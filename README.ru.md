# mytonprovider

[English version](README.md)

Менеджер для TON storage provider узлов на Linux. Устанавливает [tonutils-storage](https://github.com/xssnick/tonutils-storage) и [tonutils-storage-provider](https://github.com/xssnick/tonutils-storage-provider) как systemd сервисы и предоставляет интерактивную консоль для настройки, статуса и операций.

**Сообщество** — [@mytonprovider_chat](https://t.me/mytonprovider_chat) для вопросов и обсуждений.

## Требования

- Linux хост с Python 3.10+ или Docker 20.10+
- Доступный IPv4 с открытыми UDP портами для ADNL
- Объём диска для пространства, которое планируется предоставлять

## Модули

| Модуль                 | Обязательный | Описание                                                                                |
| ---------------------- | ------------ | --------------------------------------------------------------------------------------- |
| `mytonprovider`        | да           | Менеджер: жизненный цикл и status-панель                                                |
| `ton-storage`          | да           | Обёртка над tonutils-storage: загрузка bag'ов, хранение, раздача через ADNL             |
| `ton-storage-provider` | да           | Обёртка над tonutils-storage-provider: контракты хранения, proof'ы, выплаты             |
| `ton-wallet`           | да           | Кошелёк провайдера: импорт, экспорт, перевод, регистрация                               |
| `sys-metrics`          | да           | Локальные метрики CPU, RAM, диска и сети                                                |
| `benchmark`            | да           | Периодические бенчмарки диска и сети                                                    |
| `telemetry`            | опционально  | Периодическая статистика на mytonprovider.org; улучшает рейтинг в публичном списке      |
| `updater`              | опционально  | Ежедневное автообновление менеджера и tonutils бинарников                               |

## Установка

Скачайте установщик и запустите:

```sh
wget -O install.sh https://raw.githubusercontent.com/nessshon/mytonprovider/master/scripts/install.sh && bash install.sh
```

Установщик интерактивный — спросит про опциональные модули, путь хранилища и экономику провайдера.

<details>
<summary><strong>Через Docker</strong></summary>

### Docker run

```sh
docker run -d \
  --name mytonprovider \
  --network host \
  --restart unless-stopped \
  --stop-timeout 60 \
  -e MTP_MODULES=telemetry,updater \
  -e MTP_TON_STORAGE_PROVIDER_SPACE_GB=50 \
  -e MTP_TON_STORAGE_PROVIDER_STORAGE_COST=10 \
  -e LANG=ru \
  -v mytonprovider-src:/usr/src \
  -v mytonprovider-bin:/usr/local/bin \
  -v mytonprovider-systemd:/etc/systemd/system \
  -v mytonprovider-data:/var/lib/mytonprovider \
  -v /var/storage:/var/storage \
  ghcr.io/nessshon/mytonprovider:latest
```

Подправьте три обязательных значения (space, storage cost, host bind) под свой сетап.

### Docker Compose

**1.** Клонируйте репозиторий:

```sh
git clone https://github.com/nessshon/mytonprovider.git && cd mytonprovider
```

**2.** Скопируйте шаблон env и заполните обязательные переменные:

```sh
cp .env.example .env && nano .env
```

**3.** Запустите демон:

```sh
docker compose up -d
```

### Переменные окружения

| Переменная                                 | Обязательная | По умолчанию          | Описание                                                              |
| ------------------------------------------ | ------------ | --------------------- |-----------------------------------------------------------------------|
| `MTP_MODULES`                              | нет          | `telemetry,updater`   | Опциональные модули при первой установке, через запятую               |
| `MTP_TON_STORAGE_PATH`                     | да           | —                     | Абсолютный путь на хосте, монтируемый в `/var/storage`                |
| `MTP_TON_STORAGE_PROVIDER_SPACE_GB`        | да           | —                     | Объём диска для предоставления, в GB                                  |
| `MTP_TON_STORAGE_PROVIDER_STORAGE_COST`    | да           | —                     | Цена хранения в TON за 200 GB в месяц                                 |
| `LANG`                                     | нет          | `en`                  | Язык интерфейса: `en`, `ru`, или `zh`                                 |

Читаются один раз при первой установке для предзаполнения `mytonprovider install`. После установки маркера они не действуют — меняйте значения через консольные команды `provider`.

### Тома

| Путь в контейнере        | Назначение                                                | Источник                                  |
| ------------------------ | --------------------------------------------------------- | ----------------------------------------- |
| `/usr/src`               | Исходники под управлением `updater`                       | именованный том `mytonprovider-src`       |
| `/usr/local/bin`         | tonutils бинари, собранные в `mytonprovider install`      | именованный том `mytonprovider-bin`       |
| `/etc/systemd/system`    | Systemd unit-файлы и enable-симлинки                      | именованный том `mytonprovider-systemd`   |
| `/var/lib/mytonprovider` | Состояние приложения (БД, маркер установки, venv-симлинк) | именованный том `mytonprovider-data`      |
| `/var/storage`           | Данные хранилища (ключи, конфиги, БД, bag'и)              | bind с хоста через `MTP_TON_STORAGE_PATH` |

</details>

## Использование

Откройте консоль:

```sh
mytonprovider
```

Введите `help` для списка команд или `info` для краткого гайда по настройке.

### Первый запуск

1. Проверьте, что модули активны и порты открыты — `status`
2. Импортируйте кошелёк, опционально — `wallet import`
3. Сохраните приватный ключ в надёжном месте — `wallet export`
4. Пополните баланс и зарегистрируйте провайдера в публичном списке — `register`

После подтверждения транзакции регистрации провайдер появится в публичном списке на [mytonprovider.org](https://mytonprovider.org).

### Мониторинг провайдера

1. Включите телеметрию — `telemetry enable`
2. Задайте пароль для авторизации в боте — `telemetry password`
3. Откройте [@mytonprovider_bot](https://t.me/mytonprovider_bot) и найдите своего провайдера
4. Подпишитесь, введя заданный пароль

### Жалобы на плохие bags

1. Откройте [@bagidreport_bot](https://t.me/bagidreport_bot)
2. Отправьте bag id, на который хотите подать жалобу
3. Укажите описание и причину жалобы
4. Модераторы рассмотрят жалобу и заблокируют подтверждённые плохие bags

### Файловая система

| Путь                          | Содержимое                                                                                |
| ----------------------------- | ----------------------------------------------------------------------------------------- |
| `/usr/src/`                   | Исходники: mytonprovider, tonutils-storage, tonutils-storage-provider                     |
| `/usr/local/bin/`             | Установленные бинари: mytonprovider, tonutils, tonutils-storage, tonutils-storage-provider |
| `/var/lib/mytonprovider/`     | Состояние приложения: БД, логи, Python venv                                               |
| `/var/storage/`               | Данные провайдера: конфиги ton-storage и provider, bag'и                                  |

### Сервисы

systemd units:

| Unit                            | Назначение                       |
| ------------------------------- | -------------------------------- |
| `mytonproviderd.service`        | Daemon менеджера                 |
| `mytonprovider-updater.service` | Daemon автообновления            |
| `ton-storage.service`           | tonutils-storage daemon          |
| `ton-storage-provider.service`  | tonutils-storage-provider daemon |

### Логи

Файл лога приложения: `/var/lib/mytonprovider/mytonprovider.log`

Логи сервисов через systemd journal:

```sh
journalctl -u mytonproviderd -n 100 -f
journalctl -u mytonprovider-updater -n 100 -f
journalctl -u ton-storage -n 100 -f
journalctl -u ton-storage-provider -n 100 -f
```

### Подсказки

- Сменить язык: `db set language <ru|en|zh>`
- Debug-режим: `db set debug <true|false>`

## Удаление

```sh
mytonprovider uninstall
```

<details>
<summary><strong>Через Docker</strong></summary>

```sh
docker rm -f mytonprovider
docker volume rm mytonprovider-data mytonprovider-systemd mytonprovider-bin mytonprovider-src
```

Для Compose: `docker compose down -v`.

</details>

Данные хранилища в `/var/storage` (ключи, конфиги, БД, bag'и) остаются на диске — удалите вручную, иначе при повторной установке провайдер восстановится с теми же ключами.

## Лицензия

GPL-3.0-or-later. См. [LICENSE](LICENSE).
