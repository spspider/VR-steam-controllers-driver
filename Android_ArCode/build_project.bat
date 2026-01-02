@echo off
echo Установка JAVA_HOME для сборки...

REM Попробуем найти JDK в стандартных местах
if exist "C:\Program Files\Java\jdk-11" (
    set JAVA_HOME=C:\Program Files\Java\jdk-11
    echo Найден JDK в: %JAVA_HOME%
    goto build
)

if exist "C:\Program Files\Eclipse Adoptium\jdk-11.0.21.9-hotspot" (
    set JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-11.0.21.9-hotspot
    echo Найден JDK в: %JAVA_HOME%
    goto build
)

if exist "D:\Program_files\Android\AndroidStudio\jbr" (
    set JAVA_HOME=D:\Program_files\Android\AndroidStudio\jbr
    echo Найден JDK Android Studio в: %JAVA_HOME%
    goto build
)

echo ОШИБКА: JDK не найден!
echo Пожалуйста, установите JDK 11 или выше
echo Рекомендуется: Eclipse Temurin 11 LTS с https://adoptium.net/
pause
exit /b 1

:build
echo Сборка проекта...
gradlew.bat assembleDebug
pause