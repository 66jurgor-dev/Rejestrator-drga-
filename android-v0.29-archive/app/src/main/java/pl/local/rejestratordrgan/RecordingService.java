package pl.local.rejestratordrgan;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;

import java.io.File;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.UUID;

public class RecordingService extends Service implements SensorEventListener {
    public static final String ACTION_START = "pl.local.rejestratordrgan.START";
    public static final String ACTION_STOP = "pl.local.rejestratordrgan.STOP";
    public static final String ACTION_SET_RIDE_MODE = "pl.local.rejestratordrgan.SET_RIDE_MODE";
    public static final String ACTION_SET_SURFACE = "pl.local.rejestratordrgan.SET_SURFACE";
    public static final String EXTRA_VALUE = "value";

    private static final int NOTIFICATION_ID = 15;
    private static final String CHANNEL_ID = "recording";
    private static final long FLUSH_INTERVAL_MS = 1000L;
    private static final long TIME_SYNC_INTERVAL_MS = 60L * 1000L;
    private static final long BACKUP_INTERVAL_MS = 10L * 60L * 1000L;
    private static final long SCREEN_PULSE_INTERVAL_MS = 5L * 60L * 1000L;
    private static final long SCREEN_PULSE_DURATION_MS = 10L * 1000L;
    private static final long WAKE_LOCK_TIMEOUT_MS = 12L * 60L * 60L * 1000L;
    private static final int SENSOR_PERIOD_US = 20000;
    private static final long HEART_RATE_MAX_AGE_MS = 5000L;

    private static volatile boolean recording;
    private static volatile long startedAtElapsed;
    private static volatile long recordsWritten;
    private static volatile File currentFile;
    private static volatile File currentBackupFile;
    private static volatile int backupPartNumber;
    private static volatile String currentRideMode = "jazda";
    private static volatile String currentSurfaceType = "twarda";
    private static volatile Integer currentHeartRateBpm;
    private static volatile long currentHeartRateElapsed;
    private static volatile String heartRateStatus = "nie wybrano pulsometru";
    private static volatile CyclingSpeedBleClient.Measurement currentSpeedMeasurement;
    private static volatile String speedSensorStatus = "nie wybrano czujnika predkosci";
    private static volatile double lastSessionAverageHeartRate;
    private static volatile int lastSessionHeartRateSeconds;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private SensorManager sensorManager;
    private Sensor accelerometer;
    private Sensor gyroscope;
    private HeartRateBleClient heartRateClient;
    private CyclingSpeedBleClient cyclingSpeedClient;
    private RawBinaryWriter rawWriter;
    private PowerManager.WakeLock wakeLock;
    private PowerManager.WakeLock screenWakeLock;
    private String sessionStamp;
    private long nextBackupRotationElapsed;
    private long nextTimeSyncElapsed;
    private long heartRateSum;
    private int heartRateSampleCount;
    private long firstHeartRateElapsed;
    private long lastHeartRateElapsed;
    private boolean writeFailure;

    private final Runnable flushRunnable = new Runnable() {
        @Override
        public void run() {
            if (!recording || rawWriter == null) return;
            long nowElapsed = SystemClock.elapsedRealtime();
            long nowNs = SystemClock.elapsedRealtimeNanos();
            try {
                if (nowElapsed >= nextTimeSyncElapsed) {
                    rawWriter.addTimeSync(nowNs, System.currentTimeMillis());
                    nextTimeSyncElapsed += TIME_SYNC_INTERVAL_MS;
                }
                if (nowElapsed >= nextBackupRotationElapsed) {
                    openNextBackupFile(true);
                    nextBackupRotationElapsed += BACKUP_INTERVAL_MS;
                }
                rawWriter.flushChunk();
                recordsWritten = rawWriter.getTotalRecordCount();
            } catch (IOException error) {
                handleWriteFailure(error);
                return;
            }
            updateRunningNotification();
            handler.postDelayed(this, FLUSH_INTERVAL_MS);
        }
    };

    private final Runnable screenPulseRunnable = new Runnable() {
        @Override
        public void run() {
            if (!recording) return;
            wakeScreenForStatus();
            handler.postDelayed(this, SCREEN_PULSE_INTERVAL_MS);
        }
    };

    public static boolean isRecording() {
        return recording;
    }

    public static long getRecordsWritten() {
        return recordsWritten;
    }

    public static long getElapsedSeconds() {
        if (!recording || startedAtElapsed == 0L) return 0L;
        return (SystemClock.elapsedRealtime() - startedAtElapsed) / 1000L;
    }

    public static File getCurrentFile() {
        return currentFile;
    }

    public static File getCurrentBackupFile() {
        return currentBackupFile;
    }

    public static int getBackupPartNumber() {
        return backupPartNumber;
    }

    public static String getCurrentRideMode() {
        return currentRideMode;
    }

    public static String getCurrentSurfaceType() {
        return currentSurfaceType;
    }

    public static Integer getCurrentHeartRateBpm() {
        Integer bpm = currentHeartRateBpm;
        if (bpm == null || currentHeartRateElapsed == 0L) return null;
        if (SystemClock.elapsedRealtime() - currentHeartRateElapsed > HEART_RATE_MAX_AGE_MS) return null;
        return bpm;
    }

    public static String getHeartRateStatus() {
        return heartRateStatus;
    }

    public static Double getCurrentWheelSpeedKmh() {
        CyclingSpeedBleClient.Measurement measurement = currentSpeedMeasurement;
        return measurement == null ? null : measurement.speedKmh;
    }

    public static String getSpeedSensorStatus() {
        return speedSensorStatus;
    }

    public static double getLastSessionAverageHeartRate() {
        return lastSessionAverageHeartRate;
    }

    public static int getLastSessionHeartRateSeconds() {
        return lastSessionHeartRateSeconds;
    }

    public static void setCurrentRideMode(String mode) {
        if (mode != null && !mode.isEmpty()) currentRideMode = mode;
    }

    public static void setCurrentSurfaceType(String surface) {
        if (surface != null && !surface.isEmpty()) currentSurfaceType = surface;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        sensorManager = (SensorManager) getSystemService(SENSOR_SERVICE);
        if (sensorManager != null) {
            accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER);
            gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE);
        }
        restoreLatestSessionFiles(this);
        heartRateClient = new HeartRateBleClient(this, new HeartRateBleClient.Listener() {
            @Override
            public void onHeartRate(int bpm) {
                long nowElapsed = SystemClock.elapsedRealtime();
                currentHeartRateBpm = bpm;
                currentHeartRateElapsed = nowElapsed;
                synchronized (RecordingService.this) {
                    heartRateSum += bpm;
                    heartRateSampleCount += 1;
                    if (firstHeartRateElapsed == 0L) firstHeartRateElapsed = nowElapsed;
                    lastHeartRateElapsed = nowElapsed;
                }
                writeRecord(writer -> writer.addHeartRate(SystemClock.elapsedRealtimeNanos(), bpm));
            }

            @Override
            public void onStatusChanged(String status) {
                if (!status.equals(heartRateStatus)) {
                    heartRateStatus = status;
                    writeStatus(RawBinaryWriter.STATUS_SOURCE_HEART_RATE, status);
                }
            }
        });
        cyclingSpeedClient = new CyclingSpeedBleClient(this, new CyclingSpeedBleClient.Listener() {
            @Override
            public void onMeasurement(CyclingSpeedBleClient.Measurement measurement) {
                currentSpeedMeasurement = measurement;
                writeRecord(writer -> writer.addWheel(
                        SystemClock.elapsedRealtimeNanos(),
                        measurement.wheelRevolutions,
                        measurement.wheelEventTime,
                        measurement.speedKmh
                ));
            }

            @Override
            public void onStatusChanged(String status) {
                if (!status.equals(speedSensorStatus)) {
                    speedSensorStatus = status;
                    writeStatus(RawBinaryWriter.STATUS_SOURCE_WHEEL, status);
                }
            }
        });
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? ACTION_START : intent.getAction();
        if (ACTION_STOP.equals(action)) {
            stopRecording();
            return START_NOT_STICKY;
        }
        if (ACTION_SET_RIDE_MODE.equals(action)) {
            setCurrentRideMode(intent == null ? null : intent.getStringExtra(EXTRA_VALUE));
            writeCurrentLabel();
            updateRunningNotification();
            return START_STICKY;
        }
        if (ACTION_SET_SURFACE.equals(action)) {
            setCurrentSurfaceType(intent == null ? null : intent.getStringExtra(EXTRA_VALUE));
            writeCurrentLabel();
            updateRunningNotification();
            return START_STICKY;
        }
        startRecording();
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        stopRecording();
        super.onDestroy();
    }

    private void startRecording() {
        if (recording) return;
        if (accelerometer == null || sensorManager == null) {
            stopSelf();
            return;
        }

        long startUtcMs = System.currentTimeMillis();
        long startMonotonicNs = SystemClock.elapsedRealtimeNanos();
        startedAtElapsed = SystemClock.elapsedRealtime();
        sessionStamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date(startUtcMs));
        int wheelCircumferenceMm = getSharedPreferences(CyclingSpeedBleClient.PREFS_NAME, MODE_PRIVATE)
                .getInt(CyclingSpeedBleClient.KEY_WHEEL_CIRCUMFERENCE_MM, 0);

        try {
            currentFile = createDataFile("drgania-" + sessionStamp + ".bin");
            rawWriter = new RawBinaryWriter(
                    currentFile,
                    UUID.randomUUID(),
                    startUtcMs,
                    startMonotonicNs,
                    SENSOR_PERIOD_US,
                    wheelCircumferenceMm
            );
            backupPartNumber = 0;
            openNextBackupFile(false);
            rawWriter.addSessionEvent(startMonotonicNs, RawBinaryWriter.SESSION_START);
            rawWriter.addTimeSync(startMonotonicNs, startUtcMs);
            rawWriter.addLabel(startMonotonicNs, rideModeCode(currentRideMode), surfaceCode(currentSurfaceType));
            rawWriter.flushChunk();
        } catch (IOException error) {
            closeWriterQuietly();
            stopSelf();
            return;
        }

        recordsWritten = rawWriter.getTotalRecordCount();
        currentHeartRateBpm = null;
        currentHeartRateElapsed = 0L;
        currentSpeedMeasurement = null;
        heartRateSum = 0L;
        heartRateSampleCount = 0;
        firstHeartRateElapsed = 0L;
        lastHeartRateElapsed = 0L;
        lastSessionAverageHeartRate = 0.0;
        lastSessionHeartRateSeconds = 0;
        writeFailure = false;
        nextBackupRotationElapsed = startedAtElapsed + BACKUP_INTERVAL_MS;
        nextTimeSyncElapsed = startedAtElapsed + TIME_SYNC_INTERVAL_MS;
        recording = true;

        String heartRateAddress = getSharedPreferences(HeartRateBleClient.PREFS_NAME, MODE_PRIVATE)
                .getString(HeartRateBleClient.KEY_DEVICE_ADDRESS, null);
        String speedSensorAddress = getSharedPreferences(CyclingSpeedBleClient.PREFS_NAME, MODE_PRIVATE)
                .getString(CyclingSpeedBleClient.KEY_DEVICE_ADDRESS, null);
        acquireWakeLock();
        startRecordingForeground(heartRateAddress, speedSensorAddress);
        sensorManager.registerListener(this, accelerometer, SENSOR_PERIOD_US);
        if (gyroscope != null) sensorManager.registerListener(this, gyroscope, SENSOR_PERIOD_US);
        heartRateClient.start(heartRateAddress);
        cyclingSpeedClient.start(speedSensorAddress, wheelCircumferenceMm);
        handler.postDelayed(flushRunnable, FLUSH_INTERVAL_MS);
        handler.postDelayed(screenPulseRunnable, SCREEN_PULSE_INTERVAL_MS);
    }

    private void stopRecording() {
        if (!recording && rawWriter == null) {
            if (heartRateClient != null) heartRateClient.stop();
            if (cyclingSpeedClient != null) cyclingSpeedClient.stop();
            return;
        }

        recording = false;
        handler.removeCallbacks(flushRunnable);
        handler.removeCallbacks(screenPulseRunnable);
        if (sensorManager != null) sensorManager.unregisterListener(this);
        if (heartRateClient != null) heartRateClient.stop();
        if (cyclingSpeedClient != null) cyclingSpeedClient.stop();

        synchronized (this) {
            lastSessionAverageHeartRate = heartRateSampleCount > 0
                    ? heartRateSum / (double) heartRateSampleCount
                    : 0.0;
            lastSessionHeartRateSeconds = firstHeartRateElapsed > 0L
                    ? (int) Math.max(1L, (lastHeartRateElapsed - firstHeartRateElapsed) / 1000L + 1L)
                    : 0;
        }

        if (rawWriter != null) {
            if (writeFailure) {
                rawWriter.abort();
            } else {
                try {
                    long nowNs = SystemClock.elapsedRealtimeNanos();
                    rawWriter.addTimeSync(nowNs, System.currentTimeMillis());
                    rawWriter.addSessionEvent(nowNs, RawBinaryWriter.SESSION_STOP);
                    rawWriter.close();
                    recordsWritten = rawWriter.getTotalRecordCount();
                } catch (IOException ignored) {
                    rawWriter.abort();
                }
            }
            rawWriter = null;
        }

        currentHeartRateBpm = null;
        currentHeartRateElapsed = 0L;
        heartRateStatus = "zatrzymano";
        currentSpeedMeasurement = null;
        speedSensorStatus = "zatrzymano";
        releaseWakeLock();
        releaseScreenWakeLock();
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    @Override
    public void onSensorChanged(SensorEvent event) {
        if (!recording || event == null || event.values.length < 3) return;
        float x = event.values[0];
        float y = event.values[1];
        float z = event.values[2];
        if (event.sensor.getType() == Sensor.TYPE_ACCELEROMETER) {
            writeRecord(writer -> writer.addAccelerometer(event.timestamp, x, y, z));
        } else if (event.sensor.getType() == Sensor.TYPE_GYROSCOPE) {
            writeRecord(writer -> writer.addGyroscope(event.timestamp, x, y, z));
        }
    }

    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) {
        if (!recording || sensor == null) return;
        writeStatus(
                RawBinaryWriter.STATUS_SOURCE_SERVICE,
                "sensor_accuracy type=" + sensor.getType() + " value=" + accuracy
        );
    }

    private void writeCurrentLabel() {
        writeRecord(writer -> writer.addLabel(
                SystemClock.elapsedRealtimeNanos(),
                rideModeCode(currentRideMode),
                surfaceCode(currentSurfaceType)
        ));
    }

    private void writeStatus(int source, String status) {
        writeRecord(writer -> writer.addStatus(SystemClock.elapsedRealtimeNanos(), source, status));
    }

    private void writeRecord(IoAction action) {
        if (!recording || rawWriter == null || writeFailure) return;
        try {
            action.run(rawWriter);
        } catch (IOException error) {
            handleWriteFailure(error);
        }
    }

    private void handleWriteFailure(IOException error) {
        if (writeFailure) return;
        writeFailure = true;
        heartRateStatus = "blad zapisu BIN";
        speedSensorStatus = "blad zapisu BIN";
        handler.post(this::stopRecording);
    }

    private void openNextBackupFile(boolean writeContext) throws IOException {
        backupPartNumber += 1;
        currentBackupFile = createDataFile(String.format(
                Locale.US,
                "drgania-%s-part-%03d.bin",
                sessionStamp,
                backupPartNumber
        ));
        rawWriter.setBackupFile(currentBackupFile);
        if (writeContext) {
            long nowNs = SystemClock.elapsedRealtimeNanos();
            rawWriter.addTimeSync(nowNs, System.currentTimeMillis());
            rawWriter.addLabel(nowNs, rideModeCode(currentRideMode), surfaceCode(currentSurfaceType));
        }
    }

    private File createDataFile(String fileName) {
        File dir = getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS);
        if (dir == null) dir = getFilesDir();
        if (!dir.exists()) dir.mkdirs();
        return new File(dir, fileName);
    }

    public static void restoreLatestSessionFiles(android.content.Context context) {
        File dir = context.getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS);
        if (dir == null || !dir.isDirectory()) return;

        File[] files = dir.listFiles();
        if (files == null) return;
        File latestMain = null;
        for (File file : files) {
            if (!file.isFile() || !file.getName().matches("drgania-\\d{8}-\\d{6}\\.bin")) continue;
            if (latestMain == null || file.lastModified() > latestMain.lastModified()) latestMain = file;
        }
        if (latestMain == null) return;

        currentFile = latestMain;
        String name = latestMain.getName();
        String stamp = name.substring("drgania-".length(), name.length() - ".bin".length());
        File latestBackup = null;
        int latestPart = 0;
        String backupPrefix = "drgania-" + stamp + "-part-";
        for (File file : files) {
            String fileName = file.getName();
            if (!file.isFile() || !fileName.startsWith(backupPrefix) || !fileName.endsWith(".bin")) continue;
            String partText = fileName.substring(backupPrefix.length(), fileName.length() - ".bin".length());
            try {
                int part = Integer.parseInt(partText);
                if (part > latestPart) {
                    latestPart = part;
                    latestBackup = file;
                }
            } catch (NumberFormatException ignored) {
            }
        }
        currentBackupFile = latestBackup;
        backupPartNumber = latestPart;
    }

    private int rideModeCode(String mode) {
        if ("jazda".equals(mode)) return 1;
        if ("prowadzenie".equals(mode)) return 2;
        return 0;
    }

    private int surfaceCode(String surface) {
        if ("twarda".equals(surface)) return 1;
        if ("stabilna_nat".equals(surface)) return 2;
        if ("nierownosci_stab".equals(surface)) return 3;
        if ("ruchoma_drob".equals(surface)) return 4;
        if ("ruchoma_grub".equals(surface)) return 5;
        if ("rynna".equals(surface)) return 6;
        if ("miekkie".equals(surface)) return 7;
        if ("regularne_twar".equals(surface)) return 8;
        if ("brak".equals(surface)) return 9;
        return 0;
    }

    private void closeWriterQuietly() {
        if (rawWriter == null) return;
        try {
            rawWriter.close();
        } catch (IOException ignored) {
        }
        rawWriter = null;
    }

    private void acquireWakeLock() {
        PowerManager manager = (PowerManager) getSystemService(POWER_SERVICE);
        if (manager == null) return;
        wakeLock = manager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "RejestratorDrgan:Recording");
        wakeLock.acquire(WAKE_LOCK_TIMEOUT_MS);
    }

    private void releaseWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        wakeLock = null;
    }

    @SuppressWarnings("deprecation")
    private void wakeScreenForStatus() {
        PowerManager manager = (PowerManager) getSystemService(POWER_SERVICE);
        if (manager == null) return;
        releaseScreenWakeLock();
        screenWakeLock = manager.newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "RejestratorDrgan:StatusScreen"
        );
        screenWakeLock.acquire(SCREEN_PULSE_DURATION_MS);
        updateRunningNotification();
    }

    private void releaseScreenWakeLock() {
        if (screenWakeLock != null && screenWakeLock.isHeld()) screenWakeLock.release();
        screenWakeLock = null;
    }

    private void updateRunningNotification() {
        if (!recording) return;
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.notify(
                    NOTIFICATION_ID,
                    buildNotification("BIN: " + recordsWritten + " | " + currentRideMode + " | " + currentSurfaceType)
            );
        }
    }

    private Notification buildNotification(String text) {
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return builder
                .setSmallIcon(R.drawable.ic_stat_recording)
                .setContentTitle("Rejestrator drgan")
                .setContentText(text)
                .setOngoing(true)
                .setPriority(Notification.PRIORITY_LOW)
                .build();
    }

    private void startRecordingForeground(String heartRateAddress, String speedSensorAddress) {
        Notification notification = buildNotification("Nagrywanie surowych danych BIN");
        if (Build.VERSION.SDK_INT < 29) {
            startForeground(NOTIFICATION_ID, notification);
            return;
        }
        boolean hasSelectedBluetoothSensor = (heartRateAddress != null && !heartRateAddress.isEmpty())
                || (speedSensorAddress != null && !speedSensorAddress.isEmpty());
        boolean canUseConnectedDevice = hasSelectedBluetoothSensor
                && (Build.VERSION.SDK_INT < 31
                || checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED);
        int serviceType = canUseConnectedDevice
                ? ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
                : ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC;
        startForeground(NOTIFICATION_ID, notification, serviceType);
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Rejestracja drgan",
                NotificationManager.IMPORTANCE_LOW
        );
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (manager != null) manager.createNotificationChannel(channel);
    }

    private interface IoAction {
        void run(RawBinaryWriter writer) throws IOException;
    }
}
