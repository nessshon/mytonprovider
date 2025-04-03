# добавить alias в bashrc


from mypylib import MyPyClass
from mypyconsole.mypyconsole import MyPyConsole

local = MyPyClass(__file__)
console = MyPyConsole()
console.name = "MyTonProvider"
#console.startFunction = None
#console.debug = None
console.local = local

def status_cmd():
    # что то делаем
    data = get_api_data(local.db.api.port, local.db.api.login, local.db.api.passwd)
    # print("какие то даные")
    print(data)
#end define

console.AddItem("команда", func, "Название команды")
console.AddItem("status", status_cmd, "Показать статус")

console.Run()