# Rejestrator drgan - Android v0.29-Raw-BIN

Wersja badawcza zapisujaca surowe dane jako podstawowy material z trasy.
Wczesniejsze wersje aplikacji pozostaja w osobnych folderach.

## Zapis terenowy

Aplikacja tworzy glowny plik:

```text
drgania-RRRRMMDD-GGMMSS.bin
```

BIN zawiera osobne zdarzenia z dokladnym czasem monotonicznym:

- surowe `ACC X/Y/Z` w m/s2,
- surowe `GYRO X/Y/Z` w rad/s,
- puls z Coospo HW9,
- surowa liczbe obrotow i czas zdarzenia z czujnika kola,
- predkosc obliczona przez aplikacje,
- zmiany trybu `jazda` / `prowadzenie`,
- zmiany dziewieciu etykiet nawierzchni,
- synchronizacje czasu UTC oraz statusy czujnikow.

Telefon nie oblicza na stale cech sekundowych. RMS, percentyle, pasma
czestotliwosci i inne cechy beda generowane na komputerze. Pozwala to pozniej
wybrac dowolna dlugosc okna bez ponownego przejazdu trasy.

## Odpornosc na awarie

- Plik ma naglowek z wersja formatu, UUID sesji, UTC i czasem monotonicznym.
- Dane sa zamykane w niezaleznych blokach mniej wiecej co sekunde.
- Kazdy blok ma CRC naglowka i CRC danych.
- Po awarii dekoder zachowuje wszystkie kompletne bloki i pomija urwany koniec.
- Dodatkowy plik zapasowy jest rozpoczynany co 10 minut.
- Aplikacja wykonuje `flush` po kazdym bloku.

Pelna specyfikacja znajduje sie w `VIBBIN_FORMAT.md`.

## Dekoder komputerowy

Skrypt `tools/vibbin_decoder.py` wykorzystuje tylko standardowa biblioteke
Pythona. Tworzy tekstowy CSV zdarzen oraz sprawdza CRC:

```powershell
python tools/vibbin_decoder.py drgania-20260701-090156.bin
```

Wynik:

```text
drgania-20260701-090156.events.csv
```

Test dekodera, lacznie z odzyskiwaniem urwanego pliku:

```powershell
python -m unittest discover -s tools -v
```

## Generator cech ML

`tools/vibbin_features.py` czyta BIN bez tworzenia posredniego, wielkiego CSV
zdarzen. Domyslnie generuje okna 1 s:

```powershell
python tools/vibbin_features.py drgania.bin
```

Inna dlugosc okna, na przyklad 2 s:

```powershell
python tools/vibbin_features.py drgania.bin --window 2
```

Wynik zawiera dawny zestaw 138 kolumn oraz cztery jawne pola kontroli jakosci:
`window_s`, `wheel_age_s`, `heart_rate_age_s`, `label_changed`. Okna, w ktorych
zmieniono etykiete nawierzchni lub trybu jazdy, mozna wykluczyc ze szkolenia.

Generator wymaga pakietu NumPy. Docelowo zostanie spakowany do programu EXE.

## Eksport GPXNAV

Program `VIBRAW_Dekoder.exe` ma tryb `GPXNAV (BIN + GPX)`. W tym trybie nalezy
wskazac plik BIN z telefonu oraz odpowiadajacy mu czasowo plik GPX z Garmina.
Wynik zawiera tylko dane potrzebne przegladarce tras:

- punkty trasy, wysokosc i czas z GPX,
- `shake_score` 0-100 liczony w oknach 1 s z zyroskopu,
- puls z HW9 oraz predkosc z czujnika kola przypisane do punktow wedlug UTC.

Wskaznik jest liczony jako:

```text
raw = 0.6 * gyro_3d_p95_abs + 0.4 * gyro_3d_max_abs_delta
shake_score = 100 * raw / (raw + 1 rad/s)
```

Normalizacja jest stala dla wszystkich tras: wartosc surowa `1 rad/s` daje wynik
50. Etykiety nawierzchni pozostaja w BIN jako dane treningowe i nie sa zamieniane
na ciagle odcinki trasy w GPXNAV.

Puls jest uznawany za aktualny przez 15 s od pomiaru, a predkosc kola przez 5 s.
Starsza wersja przegladarki poprawnie otworzy trase, ale zignoruje nowe pola
telemetryczne do czasu jej aktualizacji.

## Etykiety kalibracyjne

Tryb jazdy:

- `jazda`,
- `prowadzenie`.

Typ nawierzchni:

- `twarda`,
- `stabilna_nat`,
- `nierownosci_stab`,
- `ruchoma_drob`,
- `ruchoma_grub`,
- `rynna`,
- `miekkie`,
- `regularne_twar`,
- `brak`.

Postoj bedzie wykrywany podczas analizy na podstawie danych kola.

## Interfejs

Uklad przyciskow i zabezpieczenie Start/STOP przez przytrzymanie 5 sekund
pozostaly bez zmian. Przycisk `Zapisz BIN` eksportuje zakonczona sesje.
Szacowanie aktywnych kalorii po zatrzymaniu nadal wykorzystuje puls z HW9.

## Budowanie

Zbudowany APK znajduje sie w:

```text
app/build/outputs/apk/debug/app-debug.apk
```

Samo zbudowanie APK nie instaluje aplikacji na telefonie.
