

def install():
    ts = TonStorageScheme(
        host="localhost",
        port=randint(1024, 49151),
        login=generate_login(),
        password=generate_password()
    )
    with open(get_cwd() + "/credentials.txt", "w") as f:
        f.write(f"{ts.login=}")
        f.write(f"{ts.password=}")

    cmd =