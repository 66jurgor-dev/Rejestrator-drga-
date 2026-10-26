package pl.local.rejestratordrgan;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanRecord;
import android.bluetooth.le.ScanResult;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelUuid;
import android.text.InputType;
import android.view.Gravity;
import android.view.MotionEvent;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class MainActivity extends Activity {
    private static final String APP_VERSION = "0.29-Raw-BIN";
    private static final long HOLD_TO_RUN_MS = 5000L;
    private static final long BLE_SCAN_MS = 10000L;
    private static final int REQUEST_BLE_PERMISSIONS = 11;
    private static final int REQUEST_ENABLE_BLUETOOTH = 12;
    private static final int SCAN_HEART_RATE = 1;
    private static final int SCAN_SPEED = 2;
    private static final String PROFILE_PREFS = "calorie_profile";
    private static final String KEY_BODY_MASS_KG = "body_mass_kg";
    private static final int COLOR_SELECTED = 0xFF2D7D46;
    private static final int COLOR_IDLE = 0xFFE6EBEE;
    private static final int COLOR_TEXT_DARK = 0xFF172026;
    private static final int COLOR_TEXT_LIGHT = 0xFFFFFFFF;

    private static final String[] SURFACE_VALUES = {
            "twarda", "stabilna_nat", "nierownosci_stab",
            "ruchoma_drob", "ruchoma_grub", "rynna",
            "miekkie", "regularne_twar", "brak"
    };

    private static final String[] SURFACE_LABELS = {
            "Twarda", "Stabilna\nNAT", "Nierówności\nSTAB",
            "Ruchoma\nDROB", "Ruchoma\nGRUB", "Rynna",
            "Miękkie", "Regularne\nTWAR", "BRAK"
    };


    private static final int[] SURFACE_ACTIVE_COLORS = {
            0xFF777777, 0xFF58A84B, 0xFFF2CF18,
            0xFFF58B24, 0xFFDF2F2F, 0xFF2F5E8E,
            0xFF7A4A24, 0xFF9DAA55, 0xFF111111
    };

    private static final int[] SURFACE_IDLE_COLORS = {
            0xFFE0E0E0, 0xFFCDECC8, 0xFFFFF3A8,
            0xFFFFDDB8, 0xFFF4B9B9, 0xFFBFD2E4,
            0xFFE3C8AF, 0xFFE5E9BF, 0xFFD0D0D0
    };
    private final Handler handler = new Handler(Looper.getMainLooper());

    private TextView statusText;
    private TextView fileText;
    private TextView elapsedText;
    private TextView samplesText;
    private TextView vibrationText;
    private TextView detailsText;
    private TextView labelText;
    private TextView heartRateText;
    private TextView speedText;
    private Button startButton;
    private Button stopButton;
    private Button saveButton;
    private Button heartRateButton;
    private Button speedButton;
    private Button saveCircumferenceButton;
    private EditText circumferenceInput;
    private Button saveBodyMassButton;
    private EditText bodyMassInput;
    private Button rideButton;
    private Button pushButton;
    private final Button[] surfaceButtons = new Button[SURFACE_VALUES.length];
    private BluetoothLeScanner bluetoothScanner;
    private ScanCallback scanCallback;
    private AlertDialog scanDialog;
    private ArrayAdapter<String> scanAdapter;
    private final List<BluetoothDevice> scanDevices = new ArrayList<>();
    private final Set<String> scanAddresses = new HashSet<>();
    private int scanTarget = SCAN_HEART_RATE;

    private final Runnable stopBleScanRunnable = new Runnable() {
        @Override
        public void run() {
            stopBleScan();
            if (scanDevices.isEmpty()) {
                String message = scanTarget == SCAN_HEART_RATE
                        ? "Nie znaleziono pulsometru. Upewnij sie, ze HW9 jest wlaczony i zalozony."
                        : "Nie znaleziono czujnika predkosci. Obracaj kolem podczas wyszukiwania.";
                Toast.makeText(MainActivity.this, message, Toast.LENGTH_LONG).show();
            }
        }
    };

    private final Runnable refreshRunnable = new Runnable() {
        @Override
        public void run() {
            refreshUi();
            handler.postDelayed(this, 1000);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        RecordingService.restoreLatestSessionFiles(this);
        buildUi();
        requestNotificationPermission();
    }

    @Override
    protected void onResume() {
        super.onResume();
        handler.post(refreshRunnable);
    }

    @Override
    protected void onPause() {
        super.onPause();
        handler.removeCallbacks(refreshRunnable);
    }

    @Override
    protected void onDestroy() {
        stopBleScan();
        super.onDestroy();
    }

    private void buildUi() {
        int horizontalPadding = dp(14);
        int bottomPadding = dp(140);
        int topPadding = dp(36);
        if (Build.VERSION.SDK_INT >= 23) {
            int statusId = getResources().getIdentifier("status_bar_height", "dimen", "android");
            if (statusId > 0) {
                topPadding += getResources().getDimensionPixelSize(statusId);
            }
        }

        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setBackgroundColor(0xFFF4F7F8);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(horizontalPadding, topPadding, horizontalPadding, bottomPadding);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        scrollView.addView(root, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT
        ));

        TextView title = new TextView(this);
        title.setText("Rejestrator drgań v" + APP_VERSION);
        title.setTextSize(22);
        title.setTextColor(COLOR_TEXT_DARK);
        title.setGravity(Gravity.CENTER);
        title.setPadding(0, 0, 0, dp(4));
        root.addView(title, fullWidth());

        statusText = makeCardText("Gotowy");
        elapsedText = makeCardText("Czas: 0 s");
        samplesText = makeCardText("Rekordy BIN: 0");
        vibrationText = makeCardText("Drgania Z: 0.000");
        detailsText = makeCardText("Szczegóły: brak danych");
        labelText = makeCardText("Tryb: jazda | Nawierzchnia: twarda");
        heartRateText = makeCardText("Puls: -- | pulsometr nie wybrany");
        speedText = makeCardText("Predkosc kola: -- | czujnik nie wybrany");
        fileText = makeCardText("Plik: brak");

        root.addView(statusText, fullWidth());
        root.addView(elapsedText, fullWidth());
        root.addView(heartRateText, fullWidth());

        startButton = makeButton("Start", 18, dp(56));
        stopButton = makeButton("STOP", 23, dp(74));
        saveButton = makeButton("Zapisz BIN", 18, dp(54));
        heartRateButton = makeButton("Pulsometr: wybierz", 17, dp(54));
        speedButton = makeButton("Czujnik predkosci: wybierz", 17, dp(54));
        saveCircumferenceButton = makeButton("Zapisz obwod", 16, dp(54));
        circumferenceInput = new EditText(this);
        circumferenceInput.setHint("Obwod kola [mm]");
        circumferenceInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        circumferenceInput.setTextSize(17);
        circumferenceInput.setSingleLine(true);
        circumferenceInput.setMinHeight(dp(54));
        circumferenceInput.setPadding(dp(12), dp(8), dp(12), dp(8));
        circumferenceInput.setBackgroundColor(0xFFFFFFFF);
        int savedCircumference = getWheelCircumferenceMm();
        if (savedCircumference > 0) {
            circumferenceInput.setText(Integer.toString(savedCircumference));
        }
        saveBodyMassButton = makeButton("Zapisz mase", 16, dp(54));
        bodyMassInput = new EditText(this);
        bodyMassInput.setHint("Masa ciala [kg]");
        bodyMassInput.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        bodyMassInput.setTextSize(17);
        bodyMassInput.setSingleLine(true);
        bodyMassInput.setMinHeight(dp(54));
        bodyMassInput.setPadding(dp(12), dp(8), dp(12), dp(8));
        bodyMassInput.setBackgroundColor(0xFFFFFFFF);
        float savedBodyMass = getBodyMassKg();
        if (savedBodyMass > 0.0f) {
            bodyMassInput.setText(String.format(Locale.US, "%.1f", savedBodyMass));
        }

        setHoldAction(startButton, "Start", "Trzymaj 5 s: Start", this::startRecording);
        setHoldAction(stopButton, "STOP", "Trzymaj 5 s: STOP", this::stopRecording);
        saveButton.setOnClickListener(v -> saveCsv());
        heartRateButton.setOnClickListener(v -> selectHeartRateMonitor());
        speedButton.setOnClickListener(v -> selectSpeedSensor());
        saveCircumferenceButton.setOnClickListener(v -> saveWheelCircumference());
        saveBodyMassButton.setOnClickListener(v -> saveBodyMass());

        TextView modeTitle = makeSectionTitle("Tryb jazdy");
        root.addView(modeTitle, fullWidth());

        LinearLayout modeRow = new LinearLayout(this);
        modeRow.setOrientation(LinearLayout.HORIZONTAL);
        rideButton = makeButton("Jazda", 21, dp(76));
        pushButton = makeButton("Prowadzenie", 19, dp(76));
        rideButton.setOnClickListener(v -> setRideMode("jazda"));
        pushButton.setOnClickListener(v -> setRideMode("prowadzenie"));
        modeRow.addView(rideButton, weightedButtonParams(1, true));
        modeRow.addView(pushButton, weightedButtonParams(1, false));
        root.addView(modeRow, fullWidth());

        TextView surfaceTitle = makeSectionTitle("Nawierzchnia");
        root.addView(surfaceTitle, fullWidth());

        for (int row = 0; row < 3; row += 1) {
            LinearLayout surfaceRow = new LinearLayout(this);
            surfaceRow.setOrientation(LinearLayout.HORIZONTAL);
            surfaceRow.setBaselineAligned(false);
            for (int column = 0; column < 3; column += 1) {
                int index = row * 3 + column;
                Button button = makeButton(SURFACE_LABELS[index], 18, dp(94));
                button.setGravity(Gravity.CENTER);
                button.setMaxLines(3);
                button.setPadding(dp(3), dp(3), dp(3), dp(3));
                final String value = SURFACE_VALUES[index];
                button.setOnClickListener(v -> setSurfaceType(value));
                surfaceButtons[index] = button;
                surfaceRow.addView(button, surfaceButtonParams(column < 2));
            }
            root.addView(surfaceRow, surfaceRowParams());
        }

        root.addView(startButton, fullWidth());
        root.addView(stopButton, fullWidth());
        root.addView(speedText, fullWidth());

        TextView sensorsTitle = makeSectionTitle("Czujniki zewnetrzne");
        root.addView(sensorsTitle, fullWidth());
        root.addView(heartRateButton, fullWidth());
        root.addView(speedButton, fullWidth());

        LinearLayout circumferenceRow = new LinearLayout(this);
        circumferenceRow.setOrientation(LinearLayout.HORIZONTAL);
        circumferenceRow.addView(circumferenceInput, weightedButtonParams(1, true));
        circumferenceRow.addView(saveCircumferenceButton, weightedButtonParams(1, false));
        root.addView(circumferenceRow, fullWidth());

        TextView caloriesTitle = makeSectionTitle("Obliczanie kalorii");
        root.addView(caloriesTitle, fullWidth());
        LinearLayout bodyMassRow = new LinearLayout(this);
        bodyMassRow.setOrientation(LinearLayout.HORIZONTAL);
        bodyMassRow.addView(bodyMassInput, weightedButtonParams(1, true));
        bodyMassRow.addView(saveBodyMassButton, weightedButtonParams(1, false));
        root.addView(bodyMassRow, fullWidth());

        root.addView(fileText, fullWidth());
        root.addView(saveButton, fullWidth());

        setContentView(scrollView);
        refreshUi();
    }

    private TextView makeCardText(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(16);
        view.setTextColor(COLOR_TEXT_DARK);
        view.setBackgroundColor(0xFFFFFFFF);
        view.setPadding(dp(12), dp(10), dp(12), dp(10));
        return view;
    }

    private TextView makeSectionTitle(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(17);
        view.setTextColor(0xFF45545C);
        view.setGravity(Gravity.CENTER);
        view.setPadding(0, dp(4), 0, 0);
        return view;
    }

    private Button makeButton(String text, int textSize, int minHeight) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(textSize);
        button.setMinHeight(minHeight);
        button.setAllCaps(false);
        button.setTextColor(COLOR_TEXT_DARK);
        return button;
    }

    private void setHoldAction(Button button, String normalText, String holdText, Runnable action) {
        final Runnable[] pending = new Runnable[1];
        button.setOnTouchListener((view, event) -> {
            if (!button.isEnabled()) return false;

            if (event.getAction() == MotionEvent.ACTION_DOWN) {
                button.setText(holdText);
                pending[0] = () -> {
                    pending[0] = null;
                    button.setText(normalText);
                    action.run();
                };
                handler.postDelayed(pending[0], HOLD_TO_RUN_MS);
                return true;
            }

            if (event.getAction() == MotionEvent.ACTION_UP || event.getAction() == MotionEvent.ACTION_CANCEL) {
                if (pending[0] != null) {
                    handler.removeCallbacks(pending[0]);
                    pending[0] = null;
                    button.setText(normalText);
                }
                return true;
            }

            return true;
        });
    }

    private LinearLayout.LayoutParams fullWidth() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, 0, 0, dp(8));
        return params;
    }

    private LinearLayout.LayoutParams weightedButtonParams(int weight, boolean withRightMargin) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight);
        if (withRightMargin) {
            params.setMargins(0, 0, dp(8), 0);
        }
        return params;
    }

    private LinearLayout.LayoutParams surfaceButtonParams(boolean withRightMargin) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(100), 1);
        if (withRightMargin) {
            params.setMargins(0, 0, dp(8), 0);
        }
        return params;
    }

    private LinearLayout.LayoutParams surfaceRowParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(100)
        );
        params.setMargins(0, 0, 0, dp(8));
        return params;
    }

    private void startRecording() {
        Intent intent = new Intent(this, RecordingService.class);
        intent.setAction(RecordingService.ACTION_START);
        if (Build.VERSION.SDK_INT >= 26) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
        refreshUi();
    }

    private void stopRecording() {
        Intent intent = new Intent(this, RecordingService.class);
        intent.setAction(RecordingService.ACTION_STOP);
        startService(intent);
        refreshUi();
        handler.postDelayed(this::showCalorieSummary, 750L);
    }

    private void setRideMode(String mode) {
        RecordingService.setCurrentRideMode(mode);
        sendLabelAction(RecordingService.ACTION_SET_RIDE_MODE, mode);
        refreshUi();
    }

    private void setSurfaceType(String surface) {
        RecordingService.setCurrentSurfaceType(surface);
        sendLabelAction(RecordingService.ACTION_SET_SURFACE, surface);
        refreshUi();
    }

    private void sendLabelAction(String action, String value) {
        if (!RecordingService.isRecording()) return;

        Intent intent = new Intent(this, RecordingService.class);
        intent.setAction(action);
        intent.putExtra(RecordingService.EXTRA_VALUE, value);
        startService(intent);
    }

    private void saveCsv() {
        File file = RecordingService.getCurrentFile();
        if (file == null || !file.exists()) return;

        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        intent.putExtra(Intent.EXTRA_TITLE, file.getName());
        startActivityForResult(intent, 20);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_ENABLE_BLUETOOTH) {
            if (resultCode == RESULT_OK) startBleScan();
            return;
        }
        if (requestCode != 20 || resultCode != RESULT_OK || data == null || data.getData() == null) {
            return;
        }

        File file = RecordingService.getCurrentFile();
        if (file == null || !file.exists()) return;

        try (FileInputStream input = new FileInputStream(file);
             OutputStream output = getContentResolver().openOutputStream(data.getData())) {
            if (output == null) return;

            byte[] buffer = new byte[8192];
            int read;
            while ((read = input.read(buffer)) != -1) {
                output.write(buffer, 0, read);
            }
        } catch (IOException ignored) {
        }
    }

    private void refreshUi() {
        boolean recording = RecordingService.isRecording();
        File file = RecordingService.getCurrentFile();
        File backupFile = RecordingService.getCurrentBackupFile();
        String mode = RecordingService.getCurrentRideMode();
        String surface = RecordingService.getCurrentSurfaceType();
        Integer heartRate = RecordingService.getCurrentHeartRateBpm();
        String selectedHeartRateName = getSelectedHeartRateName();
        Double wheelSpeed = RecordingService.getCurrentWheelSpeedKmh();
        String selectedSpeedName = getSelectedSpeedSensorName();
        int wheelCircumferenceMm = getWheelCircumferenceMm();

        statusText.setText(recording
                ? "DZIAŁA: zapis drgań i etykiet nawierzchni"
                : "Status: zatrzymano");
        elapsedText.setText("Czas: " + RecordingService.getElapsedSeconds() + " s");
        samplesText.setText("Rekordy BIN: " + RecordingService.getRecordsWritten()
                + " | część " + RecordingService.getBackupPartNumber());
        labelText.setText("Tryb: " + mode + " | Nawierzchnia: " + surface);
        if (heartRate != null) {
            heartRateText.setText("Puls: " + heartRate + " bpm | " + RecordingService.getHeartRateStatus());
        } else if (recording) {
            heartRateText.setText("Puls: -- | " + RecordingService.getHeartRateStatus());
        } else {
            heartRateText.setText(selectedHeartRateName == null
                    ? "Puls: -- | pulsometr nie wybrany"
                    : "Puls: -- | gotowy: " + selectedHeartRateName);
        }
        heartRateButton.setText(selectedHeartRateName == null
                ? "Pulsometr: wybierz"
                : "Pulsometr: " + selectedHeartRateName);
        if (wheelSpeed != null) {
            speedText.setText(String.format(
                    Locale.US,
                    "Predkosc kola: %.2f km/h | %s",
                    wheelSpeed,
                    RecordingService.getSpeedSensorStatus()
            ));
        } else if (recording) {
            speedText.setText("Predkosc kola: -- | " + RecordingService.getSpeedSensorStatus());
        } else {
            String sensorInfo = selectedSpeedName == null
                    ? "czujnik nie wybrany"
                    : "gotowy: " + selectedSpeedName;
            String circumferenceInfo = wheelCircumferenceMm > 0
                    ? " | obwod " + wheelCircumferenceMm + " mm"
                    : " | ustaw obwod kola";
            speedText.setText("Predkosc kola: -- | " + sensorInfo + circumferenceInfo);
        }
        speedButton.setText(selectedSpeedName == null
                ? "Czujnik predkosci: wybierz"
                : "Czujnik predkosci: " + selectedSpeedName);
        fileText.setText(String.format(
                Locale.US,
                "%s | backup: %s",
                file == null ? "Plik: brak" : "Plik: " + file.getName(),
                backupFile == null ? "brak" : backupFile.getName()
        ));

        if (true) {
            vibrationText.setText("STD X/Y/Z: brak danych");
            detailsText.setText("Szczegóły: brak danych");
        } else {
            vibrationText.setText(String.format(
                    Locale.US,
                    "STD X %.3f | Y %.3f | Z %.3f m/s2",
                    0.0,
                    0.0,
                    0.0
            ));
            detailsText.setText(String.format(
                    Locale.US,
                    "freq X %.0f | Y %.0f | Z %.0f | próbki %d",
                    0.0,
                    0.0,
                    0.0,
                    0
            ));
            fileText.setText(String.format(
                    Locale.US,
                    "%s | backup: %s | %.0f Hz",
                    file == null ? "Plik: brak" : "Plik: " + file.getName(),
                    backupFile == null ? "brak" : backupFile.getName(),
                    0.0
            ));
        }

        startButton.setEnabled(!recording);
        stopButton.setEnabled(recording);
        saveButton.setEnabled(!recording && file != null && file.exists());
        heartRateButton.setEnabled(!recording);
        speedButton.setEnabled(!recording);
        circumferenceInput.setEnabled(!recording);
        saveCircumferenceButton.setEnabled(!recording);
        bodyMassInput.setEnabled(!recording);
        saveBodyMassButton.setEnabled(!recording);
        updateSelectionButtons(mode, surface);
    }

    private void selectHeartRateMonitor() {
        selectBleSensor(SCAN_HEART_RATE);
    }

    private void selectSpeedSensor() {
        selectBleSensor(SCAN_SPEED);
    }

    private void selectBleSensor(int target) {
        scanTarget = target;
        if (!hasBlePermissions()) {
            requestBlePermissions();
            return;
        }
        startBleScan();
    }

    private void startBleScan() {
        if (!hasBlePermissions()) return;

        BluetoothManager manager = (BluetoothManager) getSystemService(BLUETOOTH_SERVICE);
        BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
        if (adapter == null) {
            Toast.makeText(this, "Ten telefon nie obsluguje Bluetooth.", Toast.LENGTH_LONG).show();
            return;
        }
        if (!adapter.isEnabled()) {
            try {
                startActivityForResult(new Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE), REQUEST_ENABLE_BLUETOOTH);
            } catch (SecurityException error) {
                requestBlePermissions();
            }
            return;
        }

        stopBleScan();
        bluetoothScanner = adapter.getBluetoothLeScanner();
        if (bluetoothScanner == null) {
            Toast.makeText(this, "Nie mozna uruchomic skanowania Bluetooth.", Toast.LENGTH_LONG).show();
            return;
        }

        scanDevices.clear();
        scanAddresses.clear();
        scanAdapter = new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, new ArrayList<>());
        String title = scanTarget == SCAN_HEART_RATE
                ? "Wybierz pulsometr"
                : "Wybierz czujnik predkosci";
        scanDialog = new AlertDialog.Builder(this)
                .setTitle(title)
                .setAdapter(scanAdapter, (dialog, which) -> saveSelectedBleSensor(which))
                .setNegativeButton("Anuluj", null)
                .setNeutralButton("Zapomnij", (dialog, which) -> forgetSelectedBleSensor())
                .create();
        scanDialog.setOnDismissListener(dialog -> stopBleScan());
        scanDialog.show();

        scanCallback = new ScanCallback() {
            @Override
            public void onScanResult(int callbackType, ScanResult result) {
                addScanResult(result);
            }

            @Override
            public void onBatchScanResults(List<ScanResult> results) {
                for (ScanResult result : results) addScanResult(result);
            }

            @Override
            public void onScanFailed(int errorCode) {
                Toast.makeText(MainActivity.this, "Blad skanowania Bluetooth: " + errorCode, Toast.LENGTH_LONG).show();
                stopBleScan();
            }
        };

        try {
            bluetoothScanner.startScan(scanCallback);
            handler.postDelayed(stopBleScanRunnable, BLE_SCAN_MS);
        } catch (SecurityException error) {
            requestBlePermissions();
        }
    }

    private void addScanResult(ScanResult result) {
        if (result == null || result.getDevice() == null || scanAdapter == null) return;

        BluetoothDevice device = result.getDevice();
        String address = device.getAddress();
        if (address == null || scanAddresses.contains(address)) return;

        ScanRecord record = result.getScanRecord();
        String name = record == null ? null : record.getDeviceName();
        List<ParcelUuid> services = record == null ? null : record.getServiceUuids();
        String upperName = name == null ? "" : name.toUpperCase(Locale.US);
        String fallbackName;
        if (scanTarget == SCAN_HEART_RATE) {
            boolean advertisesHeartRate = services != null
                    && services.contains(new ParcelUuid(HeartRateBleClient.HEART_RATE_SERVICE_UUID));
            boolean likelyHeartRate = upperName.contains("HW9")
                    || upperName.contains("COOSPO")
                    || upperName.contains("HEART")
                    || upperName.contains("HRM");
            if (!advertisesHeartRate && !likelyHeartRate) return;
            fallbackName = "Pulsometr BLE";
        } else {
            boolean advertisesSpeed = services != null
                    && services.contains(new ParcelUuid(CyclingSpeedBleClient.CSC_SERVICE_UUID));
            boolean likelySpeed = upperName.contains("SPEED")
                    || upperName.contains("GARMIN")
                    || upperName.contains("CSC");
            if (!advertisesSpeed && !likelySpeed) return;
            fallbackName = "Czujnik predkosci BLE";
        }

        scanAddresses.add(address);
        scanDevices.add(device);
        scanAdapter.add((name == null || name.length() == 0 ? fallbackName : name) + "\n" + address);
        scanAdapter.notifyDataSetChanged();
    }

    private void saveSelectedBleSensor(int index) {
        if (index < 0 || index >= scanDevices.size()) return;
        BluetoothDevice device = scanDevices.get(index);
        String display = scanAdapter.getItem(index);
        String name = display == null ? "BLE" : display.split("\\n", 2)[0];
        if (scanTarget == SCAN_HEART_RATE) {
            getSharedPreferences(HeartRateBleClient.PREFS_NAME, MODE_PRIVATE)
                    .edit()
                    .putString(HeartRateBleClient.KEY_DEVICE_ADDRESS, device.getAddress())
                    .putString(HeartRateBleClient.KEY_DEVICE_NAME, name)
                    .apply();
            Toast.makeText(this, "Wybrano pulsometr: " + name, Toast.LENGTH_SHORT).show();
        } else {
            getSharedPreferences(CyclingSpeedBleClient.PREFS_NAME, MODE_PRIVATE)
                    .edit()
                    .putString(CyclingSpeedBleClient.KEY_DEVICE_ADDRESS, device.getAddress())
                    .putString(CyclingSpeedBleClient.KEY_DEVICE_NAME, name)
                    .apply();
            Toast.makeText(this, "Wybrano czujnik predkosci: " + name, Toast.LENGTH_SHORT).show();
        }
        refreshUi();
    }

    private void forgetSelectedBleSensor() {
        if (scanTarget == SCAN_HEART_RATE) {
            getSharedPreferences(HeartRateBleClient.PREFS_NAME, MODE_PRIVATE)
                    .edit()
                    .remove(HeartRateBleClient.KEY_DEVICE_ADDRESS)
                    .remove(HeartRateBleClient.KEY_DEVICE_NAME)
                    .apply();
        } else {
            getSharedPreferences(CyclingSpeedBleClient.PREFS_NAME, MODE_PRIVATE)
                    .edit()
                    .remove(CyclingSpeedBleClient.KEY_DEVICE_ADDRESS)
                    .remove(CyclingSpeedBleClient.KEY_DEVICE_NAME)
                    .apply();
        }
        refreshUi();
    }

    private String getSelectedHeartRateName() {
        return getSharedPreferences(HeartRateBleClient.PREFS_NAME, MODE_PRIVATE)
                .getString(HeartRateBleClient.KEY_DEVICE_NAME, null);
    }

    private String getSelectedSpeedSensorName() {
        return getSharedPreferences(CyclingSpeedBleClient.PREFS_NAME, MODE_PRIVATE)
                .getString(CyclingSpeedBleClient.KEY_DEVICE_NAME, null);
    }

    private int getWheelCircumferenceMm() {
        return getSharedPreferences(CyclingSpeedBleClient.PREFS_NAME, MODE_PRIVATE)
                .getInt(CyclingSpeedBleClient.KEY_WHEEL_CIRCUMFERENCE_MM, 0);
    }

    private void saveWheelCircumference() {
        String text = circumferenceInput.getText().toString().trim();
        int circumference;
        try {
            circumference = Integer.parseInt(text);
        } catch (NumberFormatException error) {
            circumference = 0;
        }

        if (circumference < 500 || circumference > 4000) {
            Toast.makeText(this, "Podaj obwod kola od 500 do 4000 mm.", Toast.LENGTH_LONG).show();
            return;
        }

        getSharedPreferences(CyclingSpeedBleClient.PREFS_NAME, MODE_PRIVATE)
                .edit()
                .putInt(CyclingSpeedBleClient.KEY_WHEEL_CIRCUMFERENCE_MM, circumference)
                .apply();
        Toast.makeText(this, "Zapisano obwod kola: " + circumference + " mm", Toast.LENGTH_SHORT).show();
        refreshUi();
    }

    private float getBodyMassKg() {
        return getSharedPreferences(PROFILE_PREFS, MODE_PRIVATE)
                .getFloat(KEY_BODY_MASS_KG, 0.0f);
    }

    private void saveBodyMass() {
        String text = bodyMassInput.getText().toString().trim().replace(',', '.');
        float bodyMass;
        try {
            bodyMass = Float.parseFloat(text);
        } catch (NumberFormatException error) {
            bodyMass = 0.0f;
        }

        if (bodyMass < 20.0f || bodyMass > 300.0f) {
            Toast.makeText(this, "Podaj mase ciala od 20 do 300 kg.", Toast.LENGTH_LONG).show();
            return;
        }

        getSharedPreferences(PROFILE_PREFS, MODE_PRIVATE)
                .edit()
                .putFloat(KEY_BODY_MASS_KG, bodyMass)
                .apply();
        Toast.makeText(this, String.format(Locale.US, "Zapisano mase: %.1f kg", bodyMass), Toast.LENGTH_SHORT).show();
    }

    private void showCalorieSummary() {
        float bodyMassKg = getBodyMassKg();
        double averageHeartRate = RecordingService.getLastSessionAverageHeartRate();
        int heartRateSeconds = RecordingService.getLastSessionHeartRateSeconds();

        String message;
        if (bodyMassKg <= 0.0f) {
            message = "Nie ustawiono masy ciala. Wpisz mase i zapisz ja przed kolejnym pomiarem.";
        } else if (heartRateSeconds <= 0 || averageHeartRate <= 0.0) {
            message = "Brak danych pulsu potrzebnych do obliczenia kalorii.";
        } else {
            double durationMinutes = heartRateSeconds / 60.0;
            long activeCalories = calculateActiveCalories(averageHeartRate, durationMinutes, bodyMassKg);
            message = String.format(
                    Locale.US,
                    "Czas z pomiarem pulsu: %s\nSredni puls: %.0f bpm\nAktywne kalorie: %d kcal",
                    formatDuration(heartRateSeconds),
                    averageHeartRate,
                    activeCalories
            );
        }

        new AlertDialog.Builder(this)
                .setTitle("Podsumowanie pomiaru")
                .setMessage(message)
                .setPositiveButton("OK", null)
                .show();
    }

    private long calculateActiveCalories(double hrAvg, double durationMin, double bodyMassKg) {
        final double hrRest = 65.0;
        final double hrMax = 172.0;
        final double vo2max = 35.0;

        if (durationMin <= 0.0 || bodyMassKg <= 0.0) return 0L;

        double intensity = (hrAvg - hrRest) / (hrMax - hrRest);
        intensity = Math.max(0.0, Math.min(1.0, intensity));
        double activeKcal = intensity
                * (vo2max - 3.5)
                * bodyMassKg
                * durationMin
                * 0.005;
        return Math.round(activeKcal);
    }

    private String formatDuration(int totalSeconds) {
        int hours = totalSeconds / 3600;
        int minutes = (totalSeconds % 3600) / 60;
        int seconds = totalSeconds % 60;
        if (hours > 0) {
            return String.format(Locale.US, "%d h %02d min %02d s", hours, minutes, seconds);
        }
        return String.format(Locale.US, "%d min %02d s", minutes, seconds);
    }

    private void stopBleScan() {
        handler.removeCallbacks(stopBleScanRunnable);
        if (bluetoothScanner != null && scanCallback != null && hasBlePermissions()) {
            try {
                bluetoothScanner.stopScan(scanCallback);
            } catch (SecurityException ignored) {
            }
        }
        scanCallback = null;
        bluetoothScanner = null;
    }

    private boolean hasBlePermissions() {
        if (Build.VERSION.SDK_INT >= 31) {
            return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
                    && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
        }
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private void requestBlePermissions() {
        if (Build.VERSION.SDK_INT >= 31) {
            requestPermissions(new String[]{
                    Manifest.permission.BLUETOOTH_SCAN,
                    Manifest.permission.BLUETOOTH_CONNECT
            }, REQUEST_BLE_PERMISSIONS);
        } else {
            requestPermissions(new String[]{
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                    Manifest.permission.ACCESS_FINE_LOCATION
            }, REQUEST_BLE_PERMISSIONS);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQUEST_BLE_PERMISSIONS) return;

        boolean granted = grantResults.length > 0;
        for (int result : grantResults) {
            granted = granted && result == PackageManager.PERMISSION_GRANTED;
        }
        if (granted) {
            startBleScan();
        } else {
            Toast.makeText(this, "Bez zgody na urzadzenia w poblizu nie mozna odczytywac czujnikow.", Toast.LENGTH_LONG).show();
        }
    }

    private void updateSelectionButtons(String mode, String surface) {
        markSelected(rideButton, "jazda".equals(mode));
        markSelected(pushButton, "prowadzenie".equals(mode));
        for (int i = 0; i < surfaceButtons.length; i += 1) {
            markSurfaceSelected(surfaceButtons[i], SURFACE_VALUES[i].equals(surface), i);
        }
    }

    private void markSelected(Button button, boolean selected) {
        int color = selected ? COLOR_SELECTED : COLOR_IDLE;
        setButtonBackground(button, color, selected);
        button.setTextColor(selected ? COLOR_TEXT_LIGHT : COLOR_TEXT_DARK);
    }

    private void markSurfaceSelected(Button button, boolean selected, int index) {
        int color = selected ? SURFACE_ACTIVE_COLORS[index] : SURFACE_IDLE_COLORS[index];
        setButtonBackground(button, color, selected);
        button.setTextColor(selected && isDarkColor(color) ? COLOR_TEXT_LIGHT : COLOR_TEXT_DARK);
    }

    private void setButtonBackground(Button button, int color, boolean selected) {
        GradientDrawable background = new GradientDrawable();
        background.setColor(color);
        background.setCornerRadius(dp(4));
        background.setStroke(selected ? dp(4) : dp(1), selected ? 0xFF000000 : 0x66888888);
        button.setBackground(background);
    }

    private boolean isDarkColor(int color) {
        int red = (color >> 16) & 0xFF;
        int green = (color >> 8) & 0xFF;
        int blue = color & 0xFF;
        return (red * 299 + green * 587 + blue * 114) < 128000;
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 10);
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
