# MyTonProvider

**[Русская версия](README.ru.md)**

**MyTonProvider** is a console application that serves as a convenient wrapper for  
`ton_storage`, `ton_storage_provider`, and `ton_tunnel_provider`.  
It is designed to simplify provider management tasks on Linux systems.

![MyTonProvider Status](resources/screen.png)

---

## Modules

```bash
telemetry             - Sends telemetry to the server. Improves your provider ranking.
ton_storage           - Downloads, stores, and distributes files via the ADNL protocol.
                        Required for ton_storage_provider to work.
ton_storage_provider  - Concludes storage contracts, sends confirmations, and receives payments.
                        Allows you to earn income by storing other users' files.
ton_tunnel_provider   - Concludes traffic routing contracts. 
                        Allows you to earn income by proxying traffic through your IP.
````

---

## Installation

1. **Download and run the installer**

   ```bash
   wget https://raw.githubusercontent.com/igroman787/mytonprovider/master/scripts/install.sh
   bash install.sh
   ```

2. **Select available modules** (use the spacebar to select):

   ```bash
   [?] Select modules:
      [X] telemetry
      [X] ton-storage
      [X] ton-storage-provider
   ```

3. **Specify provider settings**

   ```bash
   [?] Storage location: /var/storage
   [?] Storage price per 200GB per month: 10
   [?] Storage maximum allocated size (disk space: 1755.99, free 1747.64): 1700
   ```

4. **Run MyTonProvider**

   ```bash
   mytonprovider
   ```

5. **Get your wallet address and top it up with 1 TON**

   ```bash
   MyTonProvider> status
   ```

6. **Register in the provider list**

   ```bash
   MyTonProvider> register
   ```

   This sends a transaction to a public blockchain address and allows users
   to find your provider for storage contracts.

7. **Done.**
   After a short time, your provider will appear in the list at
   [https://mytonprovider.org](https://mytonprovider.org)

8. **(Optional)** Make a backup of your private key in a safe place:

   ```bash
   MyTonProvider> export_wallet
   ```

### Telemetry

Telemetry helps your provider rank higher.
You can disable it if you prefer.

* **To disable during installation:**

  ```bash
  [?] Select modules:
     [ ] telemetry
     [X] ton-storage
     [X] ton-storage-provider
  ```

* **To disable after installation:**

  ```bash
  MyTonProvider> set send_telemetry false
  ```

---

## Installation using Docker

1. **Clone the repository and enter the directory**

   ```bash
   git clone --single-branch https://github.com/igroman787/mytonprovider.git
   cd mytonprovider
   ```

2. **Fill in `.env`**

   | Variable                         | Description                                                               | Example                                                   |
   | -------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------- |
   | `MYTONPROVIDER_MODULES`          | Modules to install inside the container (comma-separated, **no spaces**). | `ton-storage,ton-storage-provider,auto-updater,telemetry` |
   | `MYTONPROVIDER_STORAGE_PATH`     | **Host** path for provider data (mounted into the container).             | `/var/storage`                                            |
   | `MYTONPROVIDER_STORAGE_COST`     | Storage price (in TON).                                                   | `10`                                                      |
   | `MYTONPROVIDER_SPACE_TO_PROVIDE` | Allocated space for storage (in GB).                                      | `10`                                                      |

3. **Grant permissions for `${MYTONPROVIDER_STORAGE_PATH}` on the host**

   ```bash
   sudo mkdir -p /var/storage
   sudo chown -R 1000:1000 /var/storage
   ```

4. **Build the image**

   ```bash
   docker-compose build
   ```

5. **Start the service**

   ```bash
   docker-compose up -d
   ```

6. **Open the provider console**

   ```bash
   docker exec -it mytonprovider console
   ```

### Telemetry

Enabling telemetry improves your ranking in the providers list.
You can disable it if you prefer.

**Before installation (in `.env`):**

Remove `telemetry` from `MYTONPROVIDER_MODULES`:

```env
MYTONPROVIDER_MODULES=ton-storage,ton-storage-provider,auto-updater
```

**After installation (in the console):**

```bash
MyTonProvider> set send_telemetry false
```
