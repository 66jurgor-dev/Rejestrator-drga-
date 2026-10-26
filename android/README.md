# Rejestrator Android v0.38 ML-TEST

Źródła pochodzą z przekazanego `Rejestrator.zip`. Konfiguracja deklaruje
`versionCode 38`, `versionName "0.38-ML-TEST"`; ten sam numer zawiera MainActivity.
Użytkownik wskazał v38 ML jako wersję używaną na telefonie.
Kod źródłowy zachowano bez zmian.

Projekt zawiera obsługę akcelerometru i żyroskopu, czujnika prędkości koła BLE,
pulsometru BLE, zapis BIN oraz oznaczanie odcinków testowych ML i nawierzchni.
Oznaczenie ML-TEST nie oznacza potwierdzonej obecności modelu klasyfikującego.

## Projekt i budowanie

Otwórz ten katalog jako projekt w Android Studio.
Konfiguracja z archiwum: compileSdk/targetSdk 35, minSdk 26, AGP 8.7.3,
wrapper Gradle 9.4.1, JVM toolchain 21; poziom źródeł Java 11.
Zachowano oryginalną konfigurację. Jej zgodność i pełna kompilacja nie zostały
zweryfikowane podczas importu; nie deklarujemy gotowego środowiska budowania.

## APK

Katalog `apk/` zawiera oba oryginalne pliki APK z archiwum. Sumy SHA-256:
`apk/SHA256SUMS`. Nie przebudowywano ani nie instalowano ich podczas importu.
Nie potwierdzono ich zgodności z osobno przesłanym APK o nazwie zawierającej
`nawierzchnie` ani z aplikacją obecnie zainstalowaną na telefonie.

## Pozostałe komponenty

- `../decoder/`: dekoder SHAKE v0.29 BIN + GPX.
- `../viewer/`: przeglądarka GPXNAV.
- `../android-v0.29-archive/`: historyczny rejestrator v0.29.

Zgodność obsługi nowych znaczników odcinków ML przez istniejący dekoder wymaga
osobnego sprawdzenia. Nie należy utożsamiać odczytu surowego BIN z obsługą
wszystkich nowych metadanych treningowych.
