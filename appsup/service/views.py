#!/usr/bin/env python
#coding=utf-8

# Create your views here.
from django.http import HttpResponse
import time 
import json
import uuid
import pymongo
import logging
import traceback
import appsup.settings as settings

logger = logging.getLogger(__name__)

'''
协议描述

输入
{"token":"","service":"","method":"","params":{}}

输出
{"success":true/false,"entity":{}}

'''
#入口函数
def service(request):
	try:
		if request.method == 'GET' :
			body = request.GET.get('body')
		else:
			body = request.POST.get('body')
		logger.info("request=%s" % body)
		dbody = json.loads(body)
		(token,service,method,params) = (dbody.get('token'),dbody.get('service'),dbody.get('method'),dbody.get('params'))
		if 'user' == service: 
			s = UserService()
		else:
			raise RuntimeError('service not found')
		m = getattr(s,method)
		success = m(params,token)
	except Exception,e:
		logger.error( "exception ===> %s" % e )
		err = traceback.format_exc()
		logger.error( "exception ===> %s" % err )
		success = {'success':False,'entity':'exception'}

	return answer(success)

class Parent:
	def __init__(self):
		f = (host,port,repl) = (settings.mongo_host,settings.mongo_port,settings.mongo_replicaset)
		logger.debug( "mongodb_info::> %s ; %s ; %s" % f )
		conn = pymongo.MongoClient(host=host,port=port,replicaset=repl)
		self.conn = conn
		self.db = conn.appsup

	def timestamp(self):
		return int(time.time()*1000)
		
	def success(self,isOk,entity={}):
		if isOk :
			res = {'success':isOk,'entity':entity} 
		else:
			res = {'success':isOk,'entity':{'reason':entity}} 
		logger.info('response=%s' % res) 
		return res


class UserService(Parent) :
	'''
	用户模块
		{"service":"user", ... }
	'''
	
	def register(self,params,tk):
		'''
		注册接口, 这里只列出了必填项，其余可根据需求自行添加或减少
			?body={"service":"user","method":"register", "params":{...} }
		
		输入：
			{
				"service":"user", 
				"method":"register",
				"params":{
					"username":"xxx",
					...
				} 
			}	
		输出：
			{
				"success":true/false,
				"entity":{"token":"xxxxx"}/{"reason":"xxxxxx"}
			}		
		'''
		logger.debug('register__params==%s' % params)
		username = params['username']
		user_coll = self.db.user
		ct = self.timestamp()
		if user_coll.find_one({'username':username}):
			return {'success':False,'entity':'already_exists'}
		else:
			params['ct'] = ct 
			user_coll.insert(params)
			token_coll = self.db.token
			token = uuid.uuid4().hex
			token_coll.insert({'username':username,'token':token,'ct':ct})
		return self.success(True,{'token':token})

	def login(self,params,tk):
		'''
		登陆接口
			?body={"service":"user","method":"login", "params":{...} }
		
		输入：
			{
				"service":"user", 
				"method":"login",
				"params":{
					"username":"xxx",
					"pwd":"yyy"
				} 
			}	
		输出：
			{
				"success":true/false,
				"entity":{"token":"xxxxx"}/{"reason":"xxxxxx"}
			}		
		'''
		username = params['username']
		pwd = params['pwd']
		db = self.appsup
		user_coll = db.user
		if user_coll.find_one({'username':username,'pwd':pwd}):
			token_coll = db.token
			token = uuid.uuid4().hex
			token_coll.insert({'username':username,'token':token,'ct':self.timestamp()})
			return self.success(True,{'token':token})
		else:
			return self.success(False,'username_or_pwd_error')
		
	def logout(self,params,tk):
		'''
		注销接口
			?body={"token":"xxx","service":"user","method":"logout"}
		输入：
			{
				"token":"xxx",
				"service":"user", 
				"method":"logout"
			}	
		输出：
			{"success":true}		
		'''
		db = self.appsup
		token = params['token']
		token_coll = db.token
		token_coll.remove({'token':token})
		return self.success(True)
	
	def token(self,params,tk):
		'''
		token 校验 
			?body={"token":"xxx","service":"user","method":"token"}
		输入：
			{
				"token":"xxx",
				"service":"user", 
				"method":"token"
			}	
		输出：
			{
				"success":true/false,
				"engity":{}/{"reason":"fail_token"}
			}		

		'''
		db = self.appsup
		token = tk 
		token_coll = db.token
		if token_coll.find_one({'token':token}):
			return self.success(True)
		else:
			return self.success(False,'fail_token')

	# 更新用户数据
	def update(self,params,tk):
		db = self.appsup
		token_coll = db.token
		token = token_coll.find_one({'token':tk})
		logger.debug("user.update token=%s" % token)
		if token :
			username = token['username']
			db = self.appsup
			user_coll = db.user
			params['et'] = self.timestamp()
			user_coll.update({'username':username},{'$set':params})
			user = user_coll.find_one({'username':username},{'_id':0})
			return self.success(True,user)
		else:
			return self.success(False,'fail_token')
	
	# 获取用户数据
	def find(self,params,tk):
		db = self.appsup
		user_coll = db.user
		token_coll = db.token
		if(params):
			obj = user_coll.find_one(params,{'_id':0}) 
		else:
			token = token_coll.find_one({'token':tk})
			if token:
				username = token['username']
				obj = user_coll.find_one({'username':username},{'_id':0}) 
			else:
				return self.success(False,'not_found')	
		return self.success(True,obj)	
	
	# 获取好友列表
	def friends(self,params,tk):
		db = self.appsup
		friends_coll = db.friends
		token_coll = db.token
		user_coll = db.user
		token = token_coll.find_one({'token':tk})
		FromUser = token['username']	
		ul = friends_coll.find({'from_user':FromUser},{'_id':0,'to_user':1})
		data = []
		for u in ul :
			logger.debug("u=%s" % u)
			tu = u['to_user']
			user = user_coll.find_one({'username':tu},{'_id':0,'pwd':0})
			data.append(user)
		logger.debug('friends -> %s' % data)
		return self.success(True,data)	

	# 添加好友
	def makefriends(self,params,tk):
		db = self.appsup
		friends_coll = db.friends
		token_coll = db.token
		token = token_coll.find_one({'token':tk})
		FromUser = token['username']	
		ToUser = params['username']
		if not friends_coll.find_one({'from_user':FromUser,'to_user':ToUser}) : 
			ct = self.timestamp()
			obj = {'from_user':FromUser,'to_user':ToUser,'ct':ct}
			logger.debug('makefriends -> %s' % obj)
			friends_coll.insert(obj)
		return self.success(True)	


def answer(success):
	j = json.dumps(success)
	return HttpResponse(j,content_type="text/json ; charset=utf8")
	
