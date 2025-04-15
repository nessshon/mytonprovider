from time import time as get_float_time

def uppercase(func):
	def wrapper():
		original_result = func()
		modified_result = original_result.upper()
		return modified_result
	return wrapper
#end decorator

def test_decorator(func):
	def wrapper(*args, **kwargs):
		print("do somthing")
		return func(*args, **kwargs)
	return wrapper
#end decorator


class TimeCacheItem:
	def __init__(self, func_name, time=None, result=None):
		self.func_name = func_name
		self.time = time
		self.cache_time = 10
		self.result = result
#end class

def get_time_cache_data():
	global time_cache_data
	if time_cache_data is None:
		time_cache_data = dict()
	return time_cache_data
#end define

def get_time_cache_item(func_name):
	time_cache_data = get_time_cache_data()
	if func_name not in time_cache_data:
		time_cache_item = TimeCacheItem(func_name)
		time_cache_data[func_name] = time_cache_item
	else:
		time_cache_item = time_cache_data.get(func_name)
	return time_cache_item
#end define

def set_time_cache_item(func_name, time, result):
	time_cache_data = get_time_cache_data()
	time_cache_data[func_name] = TimeCacheItem(func_name, time, result)
#end define

def time_cache(func):
	def wrapper(*args, **kwargs):
		args_str = "".join(args)
		kwargs_str = "".join(kwargs)
		func_name = f"{func.__name__}/{args_str}/{kwargs_str}"
		time_cache_item = get_time_cache_item(func_name)
		
		time_now = int(get_float_time())
		if time_cache_item.time is None or time_cache_item.time < time_now:
			result = func(*args, **kwargs)
			set_time_cache_item(func_name, time_now, result)
		else:
			result = time_cache_item.result
		return result
	return wrapper
#end decorator





@time_cache
def get_time():
	return get_float_time()
#end define

print(get_time())
