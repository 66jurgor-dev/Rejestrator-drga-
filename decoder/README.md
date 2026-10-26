# Dekoder SHAKE v0.29 — BIN + GPX

Źródła pochodzą z przekazanego archiwum `dekoder-SHAKE-v0.29.zip`.
Kod w `tools/` zachowano bez zmian. Dokumentacja formatu pochodzi z osobno
przekazanego `VIBBIN_FORMAT.md`. Oryginalny opis wydania, obejmujący również
aplikację Android, znajduje się w [README-original-v0.29.md](README-original-v0.29.md).
Archiwum nie zawierało źródeł Androida. Plik Windows EXE nie jest częścią tego katalogu.

## Uruchomienie

Wymagany Python 3.10+ i NumPy. Interfejs okienkowy wymaga również Tkinter
(w niektórych systemach Linux instalowanego osobno jako `python3-tk`).
Poniższe polecenia wykonuj w katalogu `decoder/`:

```sh
python -m pip install -r requirements.txt
python tools/vibbin_decoder.py przejazd.bin
python tools/vibbin_features.py przejazd.bin
python tools/vibbin_gpxnav.py przejazd.bin przejazd.gpx wynik.gpxnav
python tools/vibbin_tool_gui.py
```

## Testy

```sh
python -m unittest discover -s tools -v
```

## Synchronizacja BIN–GPX

Eksport GPXNAV dopisuje telemetrię do istniejących punktów GPX według UTC.
Nie interpoluje pozycji i nie synchronizuje po odległości ani obrotach koła.
`shake_score` pochodzi z najbliższego środka jednosekundowego okna żyroskopu
(tolerancja ±1,5 s). Puls jest pobierany z ostatniego pomiaru do 15 s wstecz,
a prędkość koła do 5 s wstecz. Brak pasującego pomiaru oznacza pominięcie pola.
Zygzaki GPS nie przesuwają późniejszego dopasowania czasowego, ale nie są filtrowane.
Zegary telefonu i Garmina muszą być zgodne; dekoder nie wyrównuje ich automatycznie.
