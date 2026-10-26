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

final class HeartRateBleClient {
    interface Listener {
        void onHeartRate(int bpm);

        void onStatusChanged(String status);
    }

    static final String PREFS_NAME = "heart_rate_monitor";
    static final String KEY_DEVICE_ADDRESS = "device_address";
    static final String KEY_DEVICE_NAME = "device_name";
    static final UUID HEART_RATE_SERVICE_UUID = UUID.fromString("0000180d-0000-1000-8000-00805f9b34fb");

    private static final UUID HEART_RATE_MEASUREMENT_UUID = UUID.fromString("00002a37-0000-1000-8000-00805f9b34fb");
    private static final UUID CLIENT_CONFIG_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private static final long RECONNECT_DELAY_MS = 5000L;

    private final Context context;
    private final Listener listener;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private BluetoothGatt gatt;
    private String deviceAddress;
    private boolean active;
    private volatile int latestBpm = -1;
    private volatile long latestBpmElapsed;

    private final Runnable reconnectRunnable = new Runnable() {
        @Override
        public void run() {
            if (active) {
                connectGatt();
            }
        }
    };

    private final BluetoothGattCallback callback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt bluetoothGatt, int status, int newState) {
            if (!active) return;

            if (status == BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED) {
                notifyStatus("wyszukiwanie uslugi pulsu");
                try {
                    bluetoothGatt.discoverServices();
                } catch (SecurityException error) {
                    notifyStatus("brak uprawnienia Bluetooth");
                }
                return;
            }

            if (newState == BluetoothProfile.STATE_DISCONNECTED || status != BluetoothGatt.GATT_SUCCESS) {
                closeGatt();
                latestBpm = -1;
                latestBpmElapsed = 0L;
                notifyStatus("rozlaczony - ponawianie");
                scheduleReconnect();
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt bluetoothGatt, int status) {
            if (!active || status != BluetoothGatt.GATT_SUCCESS) {
                notifyStatus("blad odczytu uslug");
                scheduleReconnect();
                return;
            }

            BluetoothGattService service = bluetoothGatt.getService(HEART_RATE_SERVICE_UUID);
            BluetoothGattCharacteristic characteristic = service == null
                    ? null
                    : service.getCharacteristic(HEART_RATE_MEASUREMENT_UUID);
            if (characteristic == null) {
                notifyStatus("brak standardowej uslugi HR");
                return;
            }

            try {
                boolean enabled = bluetoothGatt.setCharacteristicNotification(characteristic, true);
                BluetoothGattDescriptor descriptor = characteristic.getDescriptor(CLIENT_CONFIG_UUID);
                if (!enabled || descriptor == null) {
                    notifyStatus("nie mozna wlaczyc pomiaru pulsu");
                    return;
                }

                descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                bluetoothGatt.writeDescriptor(descriptor);
                notifyStatus("polaczony - oczekiwanie na puls");
            } catch (SecurityException error) {
                notifyStatus("brak uprawnienia Bluetooth");
            }
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt bluetoothGatt, BluetoothGattCharacteristic characteristic) {
            parseHeartRate(characteristic.getValue());
        }

        @Override
        public void onCharacteristicChanged(
                BluetoothGatt bluetoothGatt,
                BluetoothGattCharacteristic characteristic,
                byte[] value
        ) {
            parseHeartRate(value);
        }
    };

    HeartRateBleClient(Context context, Listener listener) {
        this.context = context.getApplicationContext();
        this.listener = listener;
    }

    void start(String address) {
        stop();
        if (address == null || address.length() == 0) {
            notifyStatus("nie wybrano pulsometru");
            return;
        }

        deviceAddress = address;
        active = true;
        latestBpm = -1;
        latestBpmElapsed = 0L;
        connectGatt();
    }

    void stop() {
        active = false;
        handler.removeCallbacks(reconnectRunnable);
        closeGatt();
        latestBpm = -1;
        latestBpmElapsed = 0L;
    }

    Integer getFreshHeartRate(long maxAgeMs) {
        if (latestBpm <= 0 || latestBpmElapsed == 0L) return null;
        if (SystemClock.elapsedRealtime() - latestBpmElapsed > maxAgeMs) return null;
        return latestBpm;
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
            notifyStatus("laczenie z pulsometrem");
            gatt = device.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE);
        } catch (IllegalArgumentException | SecurityException error) {
            notifyStatus("nieprawidlowy pulsometr");
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

    private void parseHeartRate(byte[] value) {
        if (!active || value == null || value.length < 2) return;

        boolean isSixteenBit = (value[0] & 0x01) != 0;
        int bpm;
        if (isSixteenBit) {
            if (value.length < 3) return;
            bpm = (value[1] & 0xFF) | ((value[2] & 0xFF) << 8);
        } else {
            bpm = value[1] & 0xFF;
        }

        if (bpm <= 0) return;
        latestBpm = bpm;
        latestBpmElapsed = SystemClock.elapsedRealtime();
        notifyStatus("polaczony");
        listener.onHeartRate(bpm);
    }

    private boolean hasConnectPermission() {
        return Build.VERSION.SDK_INT < 31
                || context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }

    private void notifyStatus(String status) {
        listener.onStatusChanged(status);
    }
}
