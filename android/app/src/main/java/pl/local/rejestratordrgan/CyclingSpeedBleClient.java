package pl.local.rejestratordrgan;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;

import java.util.UUID;

final class CyclingSpeedBleClient {
    interface Listener {
        void onMeasurement(Measurement measurement);

        void onStatusChanged(String status);
    }

    static final String PREFS_NAME = "cycling_speed_sensor";
    static final String KEY_DEVICE_ADDRESS = "device_address";
    static final String KEY_DEVICE_NAME = "device_name";
    static final String KEY_WHEEL_CIRCUMFERENCE_MM = "wheel_circumference_mm";
    static final UUID CSC_SERVICE_UUID = UUID.fromString("00001816-0000-1000-8000-00805f9b34fb");

    private static final UUID CSC_MEASUREMENT_UUID = UUID.fromString("00002a5b-0000-1000-8000-00805f9b34fb");
    private static final UUID CLIENT_CONFIG_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private static final long RECONNECT_DELAY_MS = 5000L;
    private static final long STOP_TIMEOUT_MS = 10000L;

    private final Context context;
    private final Listener listener;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private BluetoothGatt gatt;
    private String deviceAddress;
    private boolean active;
    private boolean connected;
    private int wheelCircumferenceMm;
    private boolean hasMeasurement;
    private long wheelRevolutions;
    private int wheelEventTime;
    private Double speedKmh;
    private long lastMovementElapsed;

    private final Runnable reconnectRunnable = new Runnable() {
        @Override
        public void run() {
            if (active) connectGatt();
        }
    };

    private final BluetoothGattCallback callback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt bluetoothGatt, int status, int newState) {
            if (!active || bluetoothGatt != gatt) return;

            if (status == BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED) {
                notifyStatus("wyszukiwanie uslugi predkosci");
                try {
                    bluetoothGatt.discoverServices();
                } catch (SecurityException error) {
                    notifyStatus("brak uprawnienia Bluetooth");
                }
                return;
            }

            if (newState == BluetoothProfile.STATE_DISCONNECTED || status != BluetoothGatt.GATT_SUCCESS) {
                connected = false;
                closeGatt();
                notifyStatus("rozlaczony - ponawianie");
                scheduleReconnect();
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt bluetoothGatt, int status) {
            if (!active || bluetoothGatt != gatt || status != BluetoothGatt.GATT_SUCCESS) {
                notifyStatus("blad odczytu uslug");
                return;
            }

            BluetoothGattService service = bluetoothGatt.getService(CSC_SERVICE_UUID);
            BluetoothGattCharacteristic characteristic = service == null
                    ? null
                    : service.getCharacteristic(CSC_MEASUREMENT_UUID);
            if (characteristic == null) {
                notifyStatus("brak standardowej uslugi CSC");
                return;
            }

            try {
                boolean enabled = bluetoothGatt.setCharacteristicNotification(characteristic, true);
                BluetoothGattDescriptor descriptor = characteristic.getDescriptor(CLIENT_CONFIG_UUID);
                if (!enabled || descriptor == null) {
                    notifyStatus("nie mozna wlaczyc pomiaru predkosci");
                    return;
                }

                descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                bluetoothGatt.writeDescriptor(descriptor);
                connected = true;
                notifyStatus("polaczony - oczekiwanie na obrot kola");
            } catch (SecurityException error) {
                notifyStatus("brak uprawnienia Bluetooth");
            }
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt bluetoothGatt, BluetoothGattCharacteristic characteristic) {
            if (bluetoothGatt == gatt) parseMeasurement(characteristic.getValue());
        }

        @Override
        public void onCharacteristicChanged(
                BluetoothGatt bluetoothGatt,
                BluetoothGattCharacteristic characteristic,
                byte[] value
        ) {
            if (bluetoothGatt == gatt) parseMeasurement(value);
        }
    };

    CyclingSpeedBleClient(Context context, Listener listener) {
        this.context = context.getApplicationContext();
        this.listener = listener;
    }

    synchronized void start(String address, int circumferenceMm) {
        stop();
        wheelCircumferenceMm = circumferenceMm;
        if (address == null || address.length() == 0) {
            notifyStatus("nie wybrano czujnika predkosci");
            return;
        }

        deviceAddress = address;
        active = true;
        connectGatt();
    }

    synchronized void stop() {
        active = false;
        connected = false;
        handler.removeCallbacks(reconnectRunnable);
        closeGatt();
        hasMeasurement = false;
        speedKmh = null;
        lastMovementElapsed = 0L;
    }

    synchronized Measurement getCurrentMeasurement() {
        if (!connected || !hasMeasurement) return null;

        Double currentSpeed = speedKmh;
        if (lastMovementElapsed > 0L
                && SystemClock.elapsedRealtime() - lastMovementElapsed >= STOP_TIMEOUT_MS) {
            currentSpeed = 0.0;
        }
        return new Measurement(wheelRevolutions, wheelEventTime, currentSpeed);
    }

    private void connectGatt() {
        if (!active || !hasConnectPermission()) {
            notifyStatus("brak uprawnienia Bluetooth");
            return;
        }

        BluetoothManager manager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
        if (adapter == null || !adapter.isEnabled()) {
            notifyStatus("Bluetooth wylaczony");
            scheduleReconnect();
            return;
        }

        try {
            BluetoothDevice device = adapter.getRemoteDevice(deviceAddress);
            notifyStatus("laczenie z czujnikiem predkosci");
            gatt = device.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE);
        } catch (IllegalArgumentException | SecurityException error) {
            notifyStatus("nieprawidlowy czujnik predkosci");
        }
    }

    private void scheduleReconnect() {
        if (!active) return;
        handler.removeCallbacks(reconnectRunnable);
        handler.postDelayed(reconnectRunnable, RECONNECT_DELAY_MS);
    }

    private void closeGatt() {
        BluetoothGatt current = gatt;
        gatt = null;
        if (current == null) return;
        try {
            current.disconnect();
            current.close();
        } catch (SecurityException ignored) {
        }
    }

    private synchronized void parseMeasurement(byte[] value) {
        if (!active || value == null || value.length < 7) return;
        int flags = value[0] & 0xFF;
        if ((flags & 0x01) == 0) return;

        long newRevolutions = uint32(value, 1);
        int newEventTime = uint16(value, 5);
        Double newSpeed = speedKmh;
        long now = SystemClock.elapsedRealtime();

        if (hasMeasurement && newRevolutions >= wheelRevolutions) {
            long revolutionDelta = newRevolutions - wheelRevolutions;
            int eventDelta = (newEventTime - wheelEventTime) & 0xFFFF;
            if (revolutionDelta > 0L) {
                lastMovementElapsed = now;
                if (eventDelta > 0 && wheelCircumferenceMm > 0) {
                    double seconds = eventDelta / 1024.0;
                    double calculated = revolutionDelta * (wheelCircumferenceMm / 1000.0) / seconds * 3.6;
                    newSpeed = calculated <= 300.0 ? calculated : null;
                }
            }
        } else if (!hasMeasurement || newRevolutions < wheelRevolutions) {
            newSpeed = null;
            lastMovementElapsed = now;
        }

        wheelRevolutions = newRevolutions;
        wheelEventTime = newEventTime;
        speedKmh = newSpeed;
        hasMeasurement = true;
        connected = true;
        Measurement measurement = getCurrentMeasurement();
        notifyStatus("polaczony");
        if (measurement != null) listener.onMeasurement(measurement);
    }

    private long uint32(byte[] value, int offset) {
        return ((long) value[offset] & 0xFF)
                | (((long) value[offset + 1] & 0xFF) << 8)
                | (((long) value[offset + 2] & 0xFF) << 16)
                | (((long) value[offset + 3] & 0xFF) << 24);
    }

    private int uint16(byte[] value, int offset) {
        return (value[offset] & 0xFF) | ((value[offset + 1] & 0xFF) << 8);
    }

    private boolean hasConnectPermission() {
        return Build.VERSION.SDK_INT < 31
                || context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }

    private void notifyStatus(String status) {
        listener.onStatusChanged(status);
    }

    static final class Measurement {
        final long wheelRevolutions;
        final int wheelEventTime;
        final Double speedKmh;

        Measurement(long wheelRevolutions, int wheelEventTime, Double speedKmh) {
            this.wheelRevolutions = wheelRevolutions;
            this.wheelEventTime = wheelEventTime;
            this.speedKmh = speedKmh;
        }
    }
}
