#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import time
import asyncio


def measure_time(func):
	def wrapper(*args, **kwargs):
		start_time = time.time()
		result = func(*args, **kwargs)
		end_time = time.time()
		elapsed_time = round(end_time - start_time, 2)
		print(f"The function {func.__name__} take {elapsed_time} seconds")
		return result
	return wrapper
#end decorator


def sync_cook(order, time_to_prepare):
	print(f'Новый заказ: {order}')
	time.sleep(time_to_prepare)
	print(order, '- готово')
#end define

async def async_cook(order, time_to_prepare):
	print(f'Новый заказ: {order}')
	await asyncio.sleep(time_to_prepare)
	print(order, '- готово')
#end define

def sync_func():
	sync_cook('Паста', 1)
	sync_cook('Салат Цезарь', 3)
	sync_cook('Отбивные', 2)
#end define

async def async_func():
	await async_cook('Паста', 1)
	await async_cook('Салат Цезарь', 3)
	await async_cook('Отбивные', 2)
#end define

async def async_tasks():
	task1 = asyncio.create_task(async_cook('Паста', 1))
	task2 = asyncio.create_task(async_cook('Салат Цезарь', 3))
	task3 = asyncio.create_task(async_cook('Отбивные', 2))

	await task1
	await task2
	await task3
#end define

@measure_time
def func1():
	sync_func()
#end define

@measure_time
def func2():
	asyncio.run(async_func())
#end define

@measure_time
def func3():
	asyncio.run(async_tasks())
#end define


async def async_work():
	global buff
	buff = 0
	await asyncio.sleep(3)
	buff = 1
	print("check done")
#end define


async def user_worker():
	global buff
	while True:
		args = input("get args: ")
		await asyncio.sleep(0.3)
		print("work done:", args, buff)
	#end while
#end define

async def work():
	task1 = asyncio.create_task(async_work())
	task2 = asyncio.create_task(user_worker())

	await task1
	await task2
#end define




if __name__ == '__main__':

	# func1()
	# print("---")
	# func2()
	# print("---")
	# func3()

	asyncio.run(work())
#end if
