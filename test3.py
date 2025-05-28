from multiprocessing import Process, Manager
from multiprocessing.managers import BaseManager, SyncManager, DictProxy
import time


def sync_cook(order, time_to_prepare):
	print(f'Новый заказ: {order}')
	time.sleep(time_to_prepare)
	print(order, '- готово')
#end define

def sync_func():
	sync_cook('Паста', 1)
	sync_cook('Салат Цезарь', 3)
	sync_cook('Отбивные', 2)
#end define

def async_func():
	p1 = Process(target=sync_cook, args=('Паста', 1))
	p2 = Process(target=sync_cook, args=('Салат Цезарь', 3))
	p3 = Process(target=sync_cook, args=('Отбивные', 2))
	p1.start()
	p2.start()
	p3.start()
	p1.join()
	p2.join()
	p3.join()
#end define

def async_work(db, i):
	while int(db["buff2"]) != 1:
		db["buff"] = i
		print("check done:", i)
		time.sleep(i)
#end define

def user_worker(db):
	while True:
		args = input("get args: ")
		db["buff2"] = args
		print("work done:", args, db["buff"])
	#end while
#end define

def work():
	with Manager() as manager:
		db = manager.dict()
		print(type(db))
		db["buff"] = 0
		db["buff2"] = 0
		Process(target=async_work, args=(db, 0.001)).start()
		Process(target=async_work, args=(db, 0.002)).start()
		Process(target=async_work, args=(db, 0.003)).start()
		user_worker(db)
#end define




class MyDict(DictProxy):
	def __init__(self, *args, **kwargs):
		for item in args:
			self._parse_dict(item)
		self._parse_dict(kwargs)
	#end define

	def _parse_dict(self, d):
		for key, value in d.items():
			if type(value) in [dict, Dict]:
				value = Dict(value)
			if type(value) == list:
				value = self._parse_list(value)
			self[key] = value
	#end define

	def _parse_list(self, lst):
		result = list()
		for value in lst:
			if type(value) in [dict, Dict]:
				value = Dict(value)
			result.append(value)
		return result
	#end define

	def __setattr__(self, key, value):
		self[key] = value
	#end define

	def __getattr__(self, key):
		return self.get(key)
	#end define
#end class


def async_work2(db, i):
	while int(db.args) != 1:
		db.buff = i
		print("check done:", i, db.buff, db.args)
		time.sleep(i)
#end define

def user_worker2(db):
	while True:
		args = input("get args: ")
		db.args = args
		print("work done:", args, db.buff)
	#end while
#end define

def work2():
	BaseManager.register('mydict', MyDict)
	with BaseManager() as manager:
		db = manager.mydict()
		db.buff = 0
		db.args = 0
		db["buff3"] = 0
		Process(target=async_work2, args=(db, 1)).start()
		#Process(target=async_work2, args=(db, 2)).start()
		#Process(target=async_work2, args=(db, 3)).start()
		user_worker2(db)
#end define

if __name__ == '__main__':

	work2()

	
#end if