# Rejestrator drgan

Najprostsza aplikacja testowa do Chrome. Rejestruje dane z czujnika ruchu telefonu przez `Accelerometer` albo `DeviceMotionEvent`, pokazuje wykres drgan w czasie i zapisuje pomiary do CSV.

## Uruchomienie

Najpewniej uruchom strone z lokalnego serwera:

```powershell
node server.js
```

Potem otworz w Chrome:

```text
http://localhost:8000
```

Na telefonie `localhost` oznacza sam telefon, nie komputer. Do testu na telefonie najwygodniej uruchomic serwer na telefonie albo wystawic strone przez HTTPS. Czujniki w Chrome moga nie dzialac po zwyklym otwarciu pliku `index.html` ani po zwyklym adresie `http://` z innego urzadzenia.

## Dane w CSV

Plik zawiera:

- czas ISO,
- czas od startu w milisekundach,
- przyspieszenie X/Y/Z,
- obliczona wielkosc drgan,
- interwal czujnika,
- zrodlo danych.

## Dekoder BIN + GPX

Źródła dekodera SHAKE v0.29, testy i opis formatu BIN znajdują się w
[katalogu decoder](decoder/README.md).

## Elementy systemu

- **Aktualny rejestrator Android: v38 ML** — według informacji użytkownika;
  źródła tej wersji nie zostały jeszcze dostarczone.
- [Archiwalny rejestrator Android v0.29 Raw-BIN](android-v0.29-archive/ARCHIVE_INFO.md)
  — źródła, projekt Gradle, APK oraz dołączone historyczne narzędzia.
- [Dekoder SHAKE v0.29 — BIN + GPX](decoder/README.md).
- [Przeglądarka GPXNAV](viewer/README.md), wraz z przekazanym EXE Windows.
- Starszy rejestrator przeglądarkowy: pliki w katalogu głównym.

Nie potwierdzono zgodności dekodera z formatem zapisu aktualnego rejestratora v38 ML.
