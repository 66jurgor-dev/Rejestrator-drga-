package pl.local.rejestratordrgan;

import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.zip.CRC32;

final class RawBinaryWriter {
    static final int FORMAT_VERSION = 1;
    static final int HEADER_SIZE = 64;

    static final int TYPE_ACCELEROMETER = 1;
    static final int TYPE_GYROSCOPE = 2;
    static final int TYPE_HEART_RATE = 3;
    static final int TYPE_WHEEL = 4;
    static final int TYPE_LABEL = 5;
    static final int TYPE_TIME_SYNC = 6;
    static final int TYPE_STATUS = 7;
    static final int TYPE_SESSION = 8;

    static final int STATUS_SOURCE_SERVICE = 1;
    static final int STATUS_SOURCE_HEART_RATE = 2;
    static final int STATUS_SOURCE_WHEEL = 3;

    static final int SESSION_START = 1;
    static final int SESSION_STOP = 2;

    private static final byte[] FILE_MAGIC = "VIBRAW01".getBytes(StandardCharsets.US_ASCII);
    private static final int CHUNK_MAGIC = 0x43484E4B;
    private static final int MAX_CHUNK_PAYLOAD = 256 * 1024;

    private final UUID sessionId;
    private final long startUtcMs;
    private final long startMonotonicNs;
    private final int sensorPeriodUs;
    private final int wheelCircumferenceMm;
    private final ByteArrayOutputStream payloadBuffer = new ByteArrayOutputStream(8192);
    private final DataOutputStream payload = new DataOutputStream(payloadBuffer);

    private DataOutputStream primary;
    private DataOutputStream backup;
    private int chunkSequence;
    private int chunkRecordCount;
    private long chunkFirstMonotonicNs;
    private long totalRecordCount;

    RawBinaryWriter(
            File primaryFile,
            UUID sessionId,
            long startUtcMs,
            long startMonotonicNs,
            int sensorPeriodUs,
            int wheelCircumferenceMm
    ) throws IOException {
        this.sessionId = sessionId;
        this.startUtcMs = startUtcMs;
        this.startMonotonicNs = startMonotonicNs;
        this.sensorPeriodUs = sensorPeriodUs;
        this.wheelCircumferenceMm = wheelCircumferenceMm;
        primary = openFile(primaryFile);
    }

    synchronized long getTotalRecordCount() {
        return totalRecordCount;
    }

    synchronized void setBackupFile(File file) throws IOException {
        flushChunk();
        closeStream(backup);
        backup = file == null ? null : openFile(file);
    }

    synchronized void addAccelerometer(long monotonicNs, float x, float y, float z) throws IOException {
        addVectorRecord(TYPE_ACCELEROMETER, monotonicNs, x, y, z);
    }

    synchronized void addGyroscope(long monotonicNs, float x, float y, float z) throws IOException {
        addVectorRecord(TYPE_GYROSCOPE, monotonicNs, x, y, z);
    }

    synchronized void addHeartRate(long monotonicNs, int bpm) throws IOException {
        beginRecord(TYPE_HEART_RATE, 10, monotonicNs);
        payload.writeShort(bpm & 0xFFFF);
        finishRecord();
    }

    synchronized void addWheel(
            long monotonicNs,
            long wheelRevolutions,
            int wheelEventTime,
            Double speedKmh
    ) throws IOException {
        beginRecord(TYPE_WHEEL, 18, monotonicNs);
        payload.writeInt((int) (wheelRevolutions & 0xFFFFFFFFL));
        payload.writeShort(wheelEventTime & 0xFFFF);
        payload.writeFloat(speedKmh == null ? Float.NaN : speedKmh.floatValue());
        finishRecord();
    }

    synchronized void addLabel(long monotonicNs, int rideMode, int surface) throws IOException {
        beginRecord(TYPE_LABEL, 10, monotonicNs);
        payload.writeByte(rideMode & 0xFF);
        payload.writeByte(surface & 0xFF);
        finishRecord();
    }

    synchronized void addTimeSync(long monotonicNs, long utcMs) throws IOException {
        beginRecord(TYPE_TIME_SYNC, 16, monotonicNs);
        payload.writeLong(utcMs);
        finishRecord();
    }

    synchronized void addStatus(long monotonicNs, int source, String message) throws IOException {
        byte[] text = (message == null ? "" : message).getBytes(StandardCharsets.UTF_8);
        int textLength = Math.min(text.length, 1024);
        beginRecord(TYPE_STATUS, 11 + textLength, monotonicNs);
        payload.writeByte(source & 0xFF);
        payload.writeShort(textLength);
        payload.write(text, 0, textLength);
        finishRecord();
    }

    synchronized void addSessionEvent(long monotonicNs, int event) throws IOException {
        beginRecord(TYPE_SESSION, 9, monotonicNs);
        payload.writeByte(event & 0xFF);
        finishRecord();
    }

    synchronized void flushChunk() throws IOException {
        if (chunkRecordCount == 0) return;

        payload.flush();
        byte[] chunkPayload = payloadBuffer.toByteArray();
        CRC32 payloadCrc = new CRC32();
        payloadCrc.update(chunkPayload);

        ByteBuffer headerWithoutMagic = ByteBuffer.allocate(24).order(ByteOrder.BIG_ENDIAN);
        headerWithoutMagic.putInt(chunkSequence);
        headerWithoutMagic.putInt(chunkRecordCount);
        headerWithoutMagic.putInt(chunkPayload.length);
        headerWithoutMagic.putLong(chunkFirstMonotonicNs);
        headerWithoutMagic.putInt((int) payloadCrc.getValue());
        byte[] headerData = headerWithoutMagic.array();
        CRC32 headerCrc = new CRC32();
        headerCrc.update(headerData);

        writeChunk(primary, headerData, (int) headerCrc.getValue(), chunkPayload);
        if (backup != null) writeChunk(backup, headerData, (int) headerCrc.getValue(), chunkPayload);

        primary.flush();
        if (backup != null) backup.flush();
        chunkSequence += 1;
        chunkRecordCount = 0;
        chunkFirstMonotonicNs = 0L;
        payloadBuffer.reset();
    }

    synchronized void close() throws IOException {
        IOException failure = null;
        try {
            flushChunk();
        } catch (IOException error) {
            failure = error;
        }
        try {
            closeStream(primary);
        } catch (IOException error) {
            if (failure == null) failure = error;
        }
        try {
            closeStream(backup);
        } catch (IOException error) {
            if (failure == null) failure = error;
        }
        primary = null;
        backup = null;
        if (failure != null) throw failure;
    }

    synchronized void abort() {
        try {
            closeStream(primary);
        } catch (IOException ignored) {
        }
        try {
            closeStream(backup);
        } catch (IOException ignored) {
        }
        primary = null;
        backup = null;
        chunkRecordCount = 0;
        chunkFirstMonotonicNs = 0L;
        payloadBuffer.reset();
    }

    private void addVectorRecord(int type, long monotonicNs, float x, float y, float z) throws IOException {
        beginRecord(type, 20, monotonicNs);
        payload.writeFloat(x);
        payload.writeFloat(y);
        payload.writeFloat(z);
        finishRecord();
    }

    private void beginRecord(int type, int recordSize, long monotonicNs) throws IOException {
        if (chunkRecordCount > 0 && payloadBuffer.size() + recordSize + 3 > MAX_CHUNK_PAYLOAD) {
            flushChunk();
        }
        if (chunkRecordCount == 0) chunkFirstMonotonicNs = monotonicNs;
        payload.writeByte(type);
        payload.writeShort(recordSize);
        payload.writeLong(monotonicNs);
    }

    private void finishRecord() {
        chunkRecordCount += 1;
        totalRecordCount += 1L;
    }

    private DataOutputStream openFile(File file) throws IOException {
        DataOutputStream stream = new DataOutputStream(
                new BufferedOutputStream(new FileOutputStream(file, false), 64 * 1024)
        );
        stream.write(buildFileHeader());
        stream.flush();
        return stream;
    }

    private byte[] buildFileHeader() {
        ByteBuffer header = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.BIG_ENDIAN);
        header.put(FILE_MAGIC);
        header.putShort((short) FORMAT_VERSION);
        header.putShort((short) HEADER_SIZE);
        header.putLong(startUtcMs);
        header.putLong(startMonotonicNs);
        header.putLong(sessionId.getMostSignificantBits());
        header.putLong(sessionId.getLeastSignificantBits());
        header.putInt(sensorPeriodUs);
        header.putInt(wheelCircumferenceMm);
        header.putInt(0);
        header.putInt(0);
        CRC32 crc = new CRC32();
        crc.update(header.array(), 0, HEADER_SIZE - 4);
        header.putInt((int) crc.getValue());
        return header.array();
    }

    private void writeChunk(
            DataOutputStream stream,
            byte[] headerData,
            int headerCrc,
            byte[] chunkPayload
    ) throws IOException {
        stream.writeInt(CHUNK_MAGIC);
        stream.write(headerData);
        stream.writeInt(headerCrc);
        stream.write(chunkPayload);
    }

    private void closeStream(DataOutputStream stream) throws IOException {
        if (stream == null) return;
        stream.flush();
        stream.close();
    }
}
