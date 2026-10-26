# Stan prac nad v0.29-Raw-BIN

## Gotowe

- format VIBRAW v1 z naglowkiem 64 B,
- surowe zdarzenia ACC, GYRO, HEART_RATE, WHEEL, LABEL, TIME_SYNC, STATUS, SESSION,
- bloki zapisywane i flushowane co okolo 1 s,
- CRC32 naglowka pliku, naglowka bloku i danych bloku,
- glowny BIN i rotowane kopie zapasowe co 10 minut,
- zapis czasu UTC i czasu monotonicznego,
- dekoder `tools/vibbin_decoder.py` do tekstowego CSV,
- generator `tools/vibbin_features.py` tworzacy cechy ML bezposrednio z BIN,
- wybor dlugosci okna cech, np. 0.5 s, 1 s, 2 s lub 5 s,
- test pasm na sygnalach syntetycznych 3 Hz i 18 Hz,
- test dekodera, w tym odzyskanie pliku z urwanym koncem,
- kompilacja Android i lint zakonczone sukcesem,
- wersja 0.29-Raw-BIN zainstalowana na Moto G15,
- generator cech ML przetestowany na rzeczywistym BIN: 162 okna i 142 kolumny,
- czujnik kola `SPD-BLE0575398` zapisany z obwodem 2100 mm,
- test BLE: 213 zdarzen kola, predkosc 0-12.61 km/h,
- test HW9: 88 pomiarow pulsu, zakres 65-98 bpm,
- ograniczenie powtarzajacych sie rekordow statusu BLE w wersji 0.29,
- test rotacji 10 min: 67538 zdarzen, suma backupow identyczna z plikiem glownym,
- backup 002 dekoduje sie samodzielnie i zaczyna od poprawnej etykiety oraz UTC,
- test awarii: po `force-stop` odzyskano 18.175 s i 19 kompletnych blokow,
- po restarcie aplikacja automatycznie odnajduje ostatni BIN do eksportu.
- program `VIBRAW_Dekoder.exe` przebudowany i sprawdzony jako samodzielna aplikacja Windows.

## Test wykonany 2026-07-01

- 4278 zdarzen w 42 blokach,
- 2133 ACC i 2126 GYRO,
- rzeczywista czestotliwosc okolo 51.7 Hz,
- poprawne CRC wszystkich blokow,
- poprawne zmiany etykiet `jazda -> prowadzenie` i `twarda -> rynna`,
- glowny plik i backup byly identyczne bit po bicie,
- szacowany rozmiar 8 h: okolo 67 MB.

## Nastepny etap

1. Wykonac dluzsza probe terenowa z rowerem, HW9 i czujnikiem kola.
2. Po probie sprawdzic ciaglosc czasu, pulsu, predkosci i etykiet.
3. Na podstawie rzeczywistej trasy wybrac docelowe okna i cechy dla uczenia maszynowego.
