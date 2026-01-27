files needed for installation:

.\VS-GyroMouse\GyroMouse\x64\Debug\GyroMouse


GyroMouse.sys - сам драйвер (самый важный файл!)
GyroMouse.inf - файл установки
GyroMouse.cat - цифровая подпись (необязательно на время тестов)
driver.obj - промежуточный объектный файл

install dreiver via "Control panel"

# PowerShell от администратора
pnputil.exe /add-driver "D:\путь\к\GyroMouse.inf" /install


you will see Giroscopic mouse filter driver


check PID VID

Get-PnpDevice -Class Mouse | Where-Object {$_.Status -eq "OK"} | Select-Object FriendlyName, InstanceId