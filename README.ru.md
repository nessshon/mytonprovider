# MyTonProvider

**[English version](README.md)**

**MyTonProvider** — консольное приложение, служащее удобной оболочкой  
для `ton_storage`, `ton_storage_provider` и `ton_tunnel_provider`.  
Оно предназначено для управления провайдером в Linux-системах.

![MyTonProvider Status](resources/screen.png)

---

## Модули

```bash
telemetry             - Отправляет телеметрию на сервер. Повышает позицию провайдера.
ton_storage           - Скачивает, хранит и раздаёт файлы по протоколу ADNL.
                        Требуется для работы ton_storage_provider.
ton_storage_provider  - Заключает контракты на хранение, отправляет подтверждения и получает оплату.
                        Позволяет зарабатывать на хранении файлов других пользователей.
ton_tunnel_provider   - Заключает контракты на маршрутизацию трафика.
                        Позволяет получать доход за проксирование чужого трафика через ваш IP.
````

---

## Установка

1. **Скачайте установщик и запустите его**

   ```bash
   wget https://raw.githubusercontent.com/igroman787/mytonprovider/master/scripts/install.sh
   bash install.sh
   ```

2. **Выберите доступные модули** (выбор пробелом):

   ```bash
   [?] Выберите модули:
      [X] telemetry
      [X] ton-storage
      [X] ton-storage-provider
   ```

3. **Укажите параметры провайдера**

   ```bash
   [?] Путь для хранения: /var/storage
   [?] Цена за 200 ГБ в месяц: 10
   [?] Максимальный выделенный размер (всего: 1755.99, свободно 1747.64): 1700
   ```

4. **Запустите MyTonProvider**

   ```bash
   mytonprovider
   ```

5. **Получите адрес кошелька и пополните его на одну монету TON**

   ```bash
   MyTonProvider> status
   ```

6. **Зарегистрируйтесь в списке провайдеров**

   ```bash
   MyTonProvider> register
   ```

   Это действие отправит транзакцию в общий адрес блокчейна
   и позволит пользователям находить ваш провайдер для заключения договора на хранение.

7. **Готово.**
   Через некоторое время ваш провайдер появится в списке на
   [https://mytonprovider.org](https://mytonprovider.org)

8. **(Необязательно)** Сделайте резервную копию приватного ключа в надёжное место:

   ```bash
   MyTonProvider> export_wallet
   ```

### Телеметрия

Телеметрия помогает вашему провайдеру подниматься в рейтинге.
При желании её можно отключить.

* **Чтобы отключить при установке:**

  ```bash
  [?] Выберите модули:
     [ ] telemetry
     [X] ton-storage
     [X] ton-storage-provider
  ```

* **Чтобы отключить после установки:**

  ```bash
  MyTonProvider> set send_telemetry false
  ```

---

## Установка с помощью Docker

1. **Клонируйте репозиторий и перейдите в каталог**

   ```bash
   git clone --single-branch https://github.com/igroman787/mytonprovider.git
   cd mytonprovider
   ```

2. **Заполните `.env`**

   | Переменная                       | Описание                                                                     | Пример                                                    |
   | -------------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------- |
   | `MYTONPROVIDER_MODULES`          | Модули, устанавливаемые внутри контейнера (через запятую, **без пробелов**). | `ton-storage,ton-storage-provider,auto-updater,telemetry` |
   | `MYTONPROVIDER_STORAGE_PATH`     | Путь на **хосте** для данных провайдера (маунтится в контейнер).             | `/var/storage`                                            |
   | `MYTONPROVIDER_STORAGE_COST`     | Цена за хранение (в TON).                                                    | `10`                                                      |
   | `MYTONPROVIDER_SPACE_TO_PROVIDE` | Объём, выделяемый под хранение (в ГБ).                                       | `10`                                                      |

3. **Выдайте права на `${MYTONPROVIDER_STORAGE_PATH}` на хосте**

   ```bash
   sudo mkdir -p /var/storage
   sudo chown -R 1000:1000 /var/storage
   ```

4. **Соберите образ**

   ```bash
   docker-compose build
   ```

5. **Запустите сервис**

   ```bash
   docker-compose up -d
   ```

6. **Откройте консоль провайдера**

   ```bash
   docker exec -it mytonprovider console
   ```

### Телеметрия

Телеметрия помогает повысить ваш рейтинг в списке провайдеров.
Вы можете отключить её при необходимости.

**До установки (в `.env`):**

Удалите `telemetry` из `MYTONPROVIDER_MODULES`:

```env
MYTONPROVIDER_MODULES=ton-storage,ton-storage-provider,auto-updater
```

**После установки (в консоли):**

```bash
MyTonProvider> set send_telemetry false
```
