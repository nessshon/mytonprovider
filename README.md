# mytonprovider

[Русская версия](README.ru.md)

A manager for TON storage provider nodes on Linux. Installs [tonutils-storage](https://github.com/xssnick/tonutils-storage) and [tonutils-storage-provider](https://github.com/xssnick/tonutils-storage-provider) as systemd services and exposes them through an interactive console for setup, status, and operations.

**Community** — [@mytonprovider_chat](https://t.me/mytonprovider_chat) for questions and discussion.

## Requirements

- Linux host with Python 3.10+ or Docker 20.10+
- Reachable IPv4 with open UDP ports for ADNL
- Disk capacity for the space you intend to provide

## Modules

| Module                 | Required | Description                                                                              |
| ---------------------- | -------- | ---------------------------------------------------------------------------------------- |
| `mytonprovider`        | yes      | Manager package: lifecycle and status panel                                              |
| `ton-storage`          | yes      | Wraps tonutils-storage: bag download, storage, serving via ADNL                          |
| `ton-storage-provider` | yes      | Wraps tonutils-storage-provider: storage contracts, proofs, payments                     |
| `ton-wallet`           | yes      | Provider wallet: import, export, transfer, register                                      |
| `sys-metrics`          | yes      | Local CPU, RAM, disk and network metrics                                                 |
| `benchmark`            | yes      | Periodic disk and network benchmarks                                                     |
| `telemetry`            | optional | Periodic provider stats to mytonprovider.org; improves your ranking in the provider list |
| `updater`              | optional | Daily auto-update of the manager and tonutils binaries                                   |

## Install

Download the installer and run it:

```sh
curl -fsSL https://raw.githubusercontent.com/nessshon/mytonprovider/web/scripts/install.sh -o install.sh && sudo bash install.sh
```

The installer is interactive — it prompts for optional modules, the
storage path, and provider economics.

<details>
<summary><strong>Using Docker</strong></summary>

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
  -e MTP_TON_STORAGE_PROVIDER_MAX_BAG_SIZE_GB=50 \
  -e LANG=en \
  -v mytonprovider-data:/var/lib/mytonprovider \
  -v mytonprovider-systemd:/etc/systemd/system \
  -v /var/storage:/var/storage \
  ghcr.io/nessshon/mytonprovider:latest
```

Adjust the three required values (space, storage cost, host bind) to fit your setup.

### Docker Compose

**1.** Clone the repository:

```sh
git clone https://github.com/nessshon/mytonprovider.git && cd mytonprovider
```

**2.** Copy the env template and fill the required variables:

```sh
cp .env.example .env && nano .env
```

**3.** Start the daemon:

```sh
docker compose up -d
```

### Environment variables

| Variable                                   | Required | Default               | Description                                                |
| ------------------------------------------ | -------- | --------------------- |------------------------------------------------------------|
| `MTP_MODULES`                              | no       | `telemetry,updater`   | Optional modules to install on first boot, comma-separated |
| `MTP_TON_STORAGE_PATH`                     | yes      | —                     | Absolute host path mounted at `/var/storage`               |
| `MTP_TON_STORAGE_PROVIDER_SPACE_GB`        | yes      | —                     | Total disk space dedicated to providing, in GB             |
| `MTP_TON_STORAGE_PROVIDER_STORAGE_COST`    | yes      | —                     | Storage rate in TON per 200 GB per month                   |
| `MTP_TON_STORAGE_PROVIDER_MAX_BAG_SIZE_GB` | no       | `50`                  | Per-bag size limit, in GB                                  |
| `LANG`                                     | no       | `en`                  | UI language: `en`, `ru`, or `zh`                           |

These are read once at first boot to pre-fill `mytonprovider install`. After the install marker is set they have no effect — change values later via the `provider` console commands.

### Volumes

| Container path           | Purpose                                              | Backed by                                          |
| ------------------------ | ---------------------------------------------------- | -------------------------------------------------- |
| `/var/lib/mytonprovider` | App state (DB, install marker, venv symlink)         | named volume `mytonprovider-data`                  |
| `/etc/systemd/system`    | Systemd unit files and enable symlinks               | named volume `mytonprovider-systemd`               |
| `/var/storage`           | Provider storage data (keys, configs, db, bags)      | host bind via `MTP_TON_STORAGE_PATH`               |

</details>

## Usage

Open the console:

```sh
mytonprovider
```

Type `help` for the available commands.

**Setup:**

1. Verify modules are active and ports open — `status`
2. Import a wallet, optional — `wallet import`
3. Save the private key in a safe place — `wallet export`
4. Top up the balance and register the provider in the public list — `register`

**Monitoring:**

1. Enable telemetry — `telemetry enable`
2. Set the telemetry password — `telemetry password`
3. Open [@mytonprovider_bot](https://t.me/mytonprovider_bot) and find your provider
4. Subscribe by entering the password

Once the registration transaction settles, the provider appears in
the public list at [mytonprovider.org](https://mytonprovider.org).

## Uninstall

```sh
sudo mytonprovider uninstall
```

<details>
<summary><strong>Using Docker</strong></summary>

```sh
docker rm -f mytonprovider
docker volume rm mytonprovider-data mytonprovider-systemd
```

For Compose: `docker compose down -v`.

</details>

Storage data at `/var/storage` (keys, configs, db, bags) is left in
place — remove manually to abandon the provider identity.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
