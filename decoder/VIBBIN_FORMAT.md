# VIBRAW format v1

The Android recorder stores source measurements in a binary `.bin` file.
All integer values are big-endian. Sensor vectors are IEEE-754 `float32`.

## File header (64 bytes)

| Offset | Size | Field |
|---:|---:|---|
| 0 | 8 | ASCII magic `VIBRAW01` |
| 8 | 2 | format version (`1`) |
| 10 | 2 | header size (`64`) |
| 12 | 8 | session start UTC milliseconds |
| 20 | 8 | session start monotonic nanoseconds |
| 28 | 8 | UUID most-significant bits |
| 36 | 8 | UUID least-significant bits |
| 44 | 4 | requested sensor period in microseconds |
| 48 | 4 | wheel circumference in millimetres |
| 52 | 4 | flags, reserved |
| 56 | 4 | reserved |
| 60 | 4 | CRC32 of bytes 0-59 |

## Chunk header (32 bytes)

Each independently verifiable chunk contains about one second of records.

| Size | Field |
|---:|---|
| 4 | ASCII magic `CHNK` |
| 4 | chunk sequence |
| 4 | record count |
| 4 | payload size |
| 8 | first monotonic timestamp in the chunk |
| 4 | payload CRC32 |
| 4 | header CRC32 covering the previous 24 header bytes after `CHNK` |

An incomplete or invalid final chunk can be ignored without losing earlier chunks.

## Records

Every record begins with `type:uint8`, `record_size:uint16`,
`monotonic_time_ns:int64`. `record_size` includes the timestamp and payload but
does not include the type and size fields.

| Type | Name | Payload after timestamp |
|---:|---|---|
| 1 | ACC | `x,y,z:float32` in m/s2 |
| 2 | GYRO | `x,y,z:float32` in rad/s |
| 3 | HEART_RATE | `bpm:uint16` |
| 4 | WHEEL | `revolutions:uint32`, `event_time:uint16`, `speed_kmh:float32` |
| 5 | LABEL | `ride_mode:uint8`, `surface:uint8` |
| 6 | TIME_SYNC | `utc_ms:int64` |
| 7 | STATUS | `source:uint8`, `text_size:uint16`, UTF-8 text |
| 8 | SESSION | `event:uint8` (`1=start`, `2=stop`) |

Ride modes: `0=unknown`, `1=jazda`, `2=prowadzenie`.

Surfaces: `0=unknown`, `1=twarda`, `2=stabilna_nat`,
`3=nierownosci_stab`, `4=ruchoma_drob`, `5=ruchoma_grub`, `6=rynna`,
`7=miekkie`, `8=regularne_twar`, `9=brak`.
