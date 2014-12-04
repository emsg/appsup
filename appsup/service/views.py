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
import urllib,urllib2


logger = logging.getLogger(__name__)

'''
协议描述

输入
{"token":"","service":"","method":"","params":{}}

输出
{"success":true/false,"entity":{}}

'''
def service(request):
	'''
	rest 入口函数
	
	入口异常信息描述：
	<table>
		<tr>
			<td>{'success':False,'entity':{'reason':'service_not_found'}}</td>
			<td>未知的服务</td>
		</tr>
		<tr>
			<td>{'success':False,'entity':{'reason':'appid_not_register'}}</td>
			<td>未注册的appid</td>
		</tr>
		<tr>
			<td>{'success':False,'entity':{'reason':'exception'}}</td>
			<td>未知异常，需要联系开发人员</td>
		</tr>
		
	</table>
	'''
	try:
		if request.method == 'GET' :
			body = request.GET.get('body')
		else:
			body = request.POST.get('body')
		logger.info("request=%s" % body)
		dbody = json.loads(body)
		(appid,token,service,method,params) = (dbody.get('appid'),dbody.get('token'),dbody.get('service'),dbody.get('method'),dbody.get('params'))
		if settings.app_cfg.has_key(appid):
			if 'user' == service: 
				s = UserService()
			elif 'event' == service: 
				s = EventService()
			else:
				success = {'success':False,'entity':{'reason':'service_not_found'}}

			m = getattr(s,method)
			params = json.loads(params)
			success = m(params,token,appid)
		else :
			success = {'success':False,'entity':{'reason':'appid_not_register'}}
		success.update({'appid':appid})
	except Exception,e:
		logger.error( "exception ===> %s" % e )
		err = traceback.format_exc()
		logger.error( "exception ===> %s" % err )
		success = {'success':False,'entity':{'reason':'exception'}}
		
	return answer(success)

class Parent:
	def __init__(self):
		f = (host,port,repl) = (settings.mongo_host,settings.mongo_port,settings.mongo_replicaset)
		logger.debug( "mongodb_info::> %s ; %s ; %s" % f )
		conn = pymongo.MongoClient(host=host,port=int(port),replicaset=repl)
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

class EventService(Parent):
	'''
	事件模块，处理app相应事件
		{"service":"event", ... }
	'''
	def a01(self,params,tk,aid):
		'''
		用户对商品感兴趣时，app发送此事件；
			?body={"service":"event","method":"a01", "params":{...} }
		
		输入：感兴趣的服务或商品id
			{
				"appid":"999999",
				"service":"event",
				"method":"a01",
				"params":{
					"username":"产生事件的登录名",
					"product_id":"服务/商品 id"	
				}
			}	
								
		输出：服务／商品 发起人的留言信息，区分在线和不在线两种情况；
			正常：
			{
				"success":true,
				"entity":{
					"message":"服务发起人的到店欢迎信息；如果为空，则表示没有欢迎信息",
					"online":true/false //true 发起人在线，false 发起人不在线
				}
			}	
			异常：
			{
				"success":false,
				"entity":{"reason":"xxxx"}
			}		
		'''
		online = False
		# TODO 测试信息，稍后要清除
		message = "每天13～15点预约此服务，可享受7折优惠，具体优惠细节可以详谈。"
		product_coll = self.db.product
		obj = product_coll.find_one({'product_id':params.get('product_id')},{'cb':1,'welcome':1,'_id':0})
		if obj :
			cb = obj.get('cb')
			cfg = settings.app_cfg
			domain,license = cfg.get(aid).get('domain'),cfg.get(aid).get('license')
			success = emsg_rest('emsg_session','is_online',{'domain':domain,'license':license,'uid':cb},aid)
			if success and success.get('success'):
				online = success.get('entity')
				message = obj.get('welcome')
		return self.success(True,{'message':message,'online':online})
	
	
class UserService(Parent) :
	'''
	用户模块
		{"service":"user", ... }
	'''
	
	def register(self,params,tk,aid):
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
		if user_coll.find_one({'username':username,'appid':aid}):
			return self.success(False,entity='already_exists')
		else:
			params['ct'] = ct 
			params['appid'] = aid
			user_coll.insert(params)
			token_coll = self.db.token
			token = uuid.uuid4().hex
			token_coll.insert({'username':username,'token':token,'ct':ct,'appid':aid})
		return self.success(True,{'token':token})

	def login(self,params,tk,aid):
		'''
		登陆接口
			?body={"service":"user","method":"login", "params":{...} }
		
		输入：
			{
				"appid":"999999",
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
		user_coll = self.db.user
		if user_coll.find_one({'username':username,'pwd':pwd,'appid':aid}):
			token_coll = self.db.token
			token = uuid.uuid4().hex
			token_coll.insert({'username':username,'token':token,'ct':self.timestamp(),'appid':aid})
			return self.success(True,{'token':token})
		else:
			return self.success(False,'username_or_pwd_error')
		
	def logout(self,params,tk,aid):
		'''
		注销接口
			?body={"token":"xxx","service":"user","method":"logout"}
		输入：
			{
				"appid":"999999",
				"token":"xxx",
				"service":"user", 
				"method":"logout"
			}	
		输出：
			{"success":true}		
		'''
		token_coll = self.db.token
		token_coll.remove({'token':tk})
		return self.success(True)
	
	def token(self,params,tk,aid):
		'''
		token 校验 
			?body={"token":"xxx","service":"user","method":"token"}
		输入：
			{
				"appid":"999999",
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
		token = tk 
		token_coll = self.db.token
		if token_coll.find_one({'token':token}):
			return self.success(True)
		else:
			return self.success(False,'fail_token')

	def update(self,params,tk,aid):
		'''
		更新用户数据时，token 是必填项，后台根据token得到用户的原始数据，其中用户的登录名不允许修改;
		更新成功后，返回更新后的用户信息
			?body={"token":"xxx","service":"user","method":"update"}
		输入：
			{
				"appid":"999999",
				"token":"xxx",
				"service":"user", 
				"method":"update",
				"params":{
					...
				}
			}	
		输出：
			{
				"success":true/false,
				"engity":{"username":"xxx",...}/{"reason":"fail_token"}
			}	
		'''
		token_coll = self.db.token
		token = token_coll.find_one({'token':tk})
		logger.debug("user.update token=%s" % token)
		if token :
			username = token['username']
			db = self.appsup
			user_coll = db.user
			params['et'] = self.timestamp()
			user_coll.update({'username':username,'appid':aid},{'$set':params})
			user = user_coll.find_one({'username':username,'appid':aid},{'_id':0})
			return self.success(True,user)
		else:
			return self.success(False,'fail_token')
	
	def find(self,params,tk,aid):
		'''
		获取用户数据,
			1、根据 token 获取对应用户的全部信息
			2、根据params中的查询条件，过滤用户信息,当 params 为空时，则根据 token 获取当前用户信息
			
			?body={"token":"xxx","service":"user","method":"find"}
		输入：
			{
				"appid":"999999",
				"token":"xxx",
				"service":"user", 
				"method":"find"
			}	
		输出：
			{
				"success":true/false,
				"engity":{"username":"xxx",...}/{"reason":"fail_token"}
			}	
		'''
		user_coll = self.db.user
		token_coll = self.db.token
		if(params):
			params.update({'appid':aid})
			obj = user_coll.find_one(params,{'_id':0}) 
		else:
			token = token_coll.find_one({'token':tk})
			if token:
				username = token['username']
				obj = user_coll.find_one({'username':username,'appid':aid},{'_id':0}) 
			else:
				return self.success(False,'not_found')	
		return self.success(True,obj)	
	
	def friends(self,params,tk,aid):
		'''
		获取好友列表,token 为必填项，获取 token 对应用户的好友列表
			?body={"token":"xxx","service":"user","method":"friends"}
		输入：
			{
				"appid":"999999",
				"token":"xxx",
				"service":"user", 
				"method":"friends"
			}	
		输出：
			{
				"success":true/false,
				"engity":{"username":"xxx",...}/{"reason":"fail_token"}
			}
		'''
		friends_coll = self.db.friends
		token_coll = self.db.token
		user_coll = self.db.user
		token = token_coll.find_one({'token':tk})
		FromUser = token['username']	
		ul = friends_coll.find({'from_user':FromUser,'appid':aid},{'_id':0,'to_user':1})
		data = []
		for u in ul :
			logger.debug("u=%s" % u)
			tu = u['to_user']
			user = user_coll.find_one({'username':tu,'appid':aid},{'_id':0,'pwd':0})
			data.append(user)
		logger.debug('friends -> %s' % data)
		return self.success(True,data)	

	def makefriends(self,params,tk,aid):
		'''
		添加好友,token 为必填项，获取 token 对应用户的好友列表
			?body={"token":"xxx","service":"user","method":"makefriends"}
		输入：
			{
				"appid":"999999",
				"token":"xxx",
				"service":"user", 
				"method":"makefriends",
				"params":{
					"username":"我要加为好友的 username"
				}
			}	
		输出：
			{
				"success":true"
			}
		'''
		friends_coll = self.db.friends
		token_coll = self.db.token
		token = token_coll.find_one({'token':tk})
		FromUser = token['username']	
		ToUser = params['username']
		if not friends_coll.find_one({'from_user':FromUser,'to_user':ToUser,'appid':aid}) : 
			ct = self.timestamp()
			obj = {'from_user':FromUser,'to_user':ToUser,'ct':ct,'appid':aid}
			logger.debug('makefriends -> %s' % obj)
			friends_coll.insert(obj)
		return self.success(True)	


def answer(success):
	j = json.dumps(success)
	return HttpResponse(j,content_type="text/json ; charset=utf8")
	

def emsg_rest(service,method,params,aid):
	'''
	请求emsg的业务接口
	'''
	try:
		body = {
			'sn':uuid.uuid4().hex,
			'service':service,
			'params':params
		}
		logger.debug('call_emsg_rest__body=%s' % body)
		body = urllib.urlencode(body)
		request = urllib2.Request(settings.emsg_rest)
		request.add_data(body)
		response = urllib2.urlopen(request)
		result = response.read()
		logger.debug('call_emsg_rest__response=%s' % result)
		return json.loads(result)
	except:
		logger.error("call_emsg_rest__error")
		return {'success':False,'entity':'error'}
	