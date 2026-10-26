# Przeglądarka GPXNAV

Przeglądanie tras i telemetrii z dekodera BIN + GPX.
Źródła z przekazanego archiwum `__pycache__.zip` zachowano bez zmian,
pomijając pamięć podręczną Pythona.

## Uruchomienie

Wymagany Python 3.10+ i Flask. W katalogu `viewer/`:

```sh
python -m pip install -r requirements.txt
python trasy_app.py
```

Serwer uruchamia się lokalnie na porcie 5020 i otwiera przeglądarkę.
Pliki `.gpxnav` umieszczaj w utworzonym katalogu `GPXNAV/`.
Starsze GPX: `GPXOLD/`; eksport: `Pobrane/`.
`GPX_PORT` zmienia port; `GPX_NO_BROWSER=1` wyłącza otwieranie przeglądarki.
`GPX_APP_DIR` wskazuje istniejący katalog danych.
Mapa i biblioteki z sieci wymagają Internetu.

Obsługiwane pola: `shake_score`, `heart_rate_bpm`, `wheel_speed_kmh`, `ride_mode`.
Dostępny jest także starszy import GPX + CSV.

## Windows

`windows/GPXtrasy_naw.exe` to oryginalny plik przekazany przez użytkownika.
Nie był tutaj uruchamiany ani budowany ponownie. Zgodność EXE ze źródłami
nie została niezależnie potwierdzona; data pliku nie jest takim potwierdzeniem.
Suma kontrolna: `windows/SHA256SUMS`.

## Testy

W katalogu `viewer/`:

```sh
python -m unittest discover -s tests -v
node tests/test_segment_processing.js
node tests/test_shake_processing.js
```
