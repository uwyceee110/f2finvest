# 导入函数库
import jqdata
from decimal import *
import time
import functools

# 初始化函数，设定基准等等
def initialize(context): 
    # 设定沪深300作为基准
    set_benchmark('000300.XSHG')
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 输出内容到日志 log.info()
    log.info('初始函数开始运行且全局只运行一次')
    # 过滤掉order系列API产生的比error级别低的log
    log.set_level('order', 'error')
    ### 股票相关设定 ###
    # 股票类每笔交易时的手续费是：买入时佣金万分之三，卖出时佣金万分之三加千分之一印花税, 每笔交易佣金最低扣5块钱
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003, close_commission=0.0003, min_commission=5), type='stock')
    ## 运行函数（reference_security为运行时间的参考标的；传入的标的只做种类区分，因此传入'000300.XSHG'或'510300.XSHG'是一样的）
      # 开盘前运行
    run_daily(before_market_open, time='before_open', reference_security='000300.XSHG') 
      # 开盘时运行
    run_daily(market_open, time='every_bar', reference_security='000300.XSHG')
      # 收盘后运行
    run_daily(after_market_close, time='after_close', reference_security='000300.XSHG')
    
    #stockCode:{是否持仓,持仓份数,T0操作份数},如不持仓，则有信号的时候买入持仓份数。{'000651.XSHE': [0,5000份,1000份],'600570.XSHG': [1,3000份,1000份]}
    g.initStocks = {'600606.XSHG': [0,6000,6000],'601166.XSHG': [0,6000,6000],'601601.XSHG': [0,3000,3000],'601688.XSHG': [0,3000,3000],'000651.XSHE': [0,3000,3000]}
    # g.initStocks = {'600570.XSHG': [0,6000,3000]}
    
    #存取上一个bar的ma5,ma10,ma20,ma30,ma60。每次开盘前重新初始化
    g.__bstockMaAndVol = {}
    
    g.__dealStockDict = {}
    #当日操作股票的买入，卖出数量
    g.__operStock = {}
    
    g.__minutes = 60
    
## 开盘前运行函数     
def before_market_open(context):
    #存取上一个bar的ma5,ma10,ma20,ma30,ma60。每次开盘前重新初始化(context,dealStockDict,maHead,volHead,minutes,field):
    g.__bstockMaAndVol = getPbxData(context,g.initStocks,'bma','bvol',g.__minutes,'close')
    g.__dealStockDict = getStockCounts(context)
    log.info('__dealStockDict',g.__dealStockDict)
    
## 开盘时运行函数
def market_open(context):
    #实盘需要取的时间
    #passMinute = time.strftime('%H:%M',time.localtime(time.time()))
    #回测取时间的方法
    runMinute = context.current_dt.minute
    runHour = context.current_dt.hour
    passMinute = str(runHour)+':'+str(runMinute)
    
    if passMinute == '9:30' or passMinute == '15:00':
        return
    
    dealMinute = context.current_dt.minute
    #因为3分钟瀑布线，只需要3分钟时执行程序
    if int(dealMinute) % g.__minutes == 0:
        # log.info('函数运行时间(market_open):'+str(context.current_dt.time()))
        nstockMaAndVol = getPbxData(context,g.__dealStockDict,'nma','nvol',g.__minutes,'close')
        changeDict = getPbxData(context,g.__dealStockDict,'bma','bvol',g.__minutes,'close')
        # log.info('当前bar数据:',nstockMaAndVol)
        for stockCode in g.__dealStockDict.keys():
            buySingal = isBuySingal(context,stockCode,g.__bstockMaAndVol,nstockMaAndVol,'bma','nma','bvol','nvol')
            sellSingal = isSellSingal(context,stockCode,g.__bstockMaAndVol,nstockMaAndVol,'bma','nma','bvol','nvol',g.__minutes)
            #如果同时满足买入和卖出。进行卖出
            if (buySingal and sellSingal):
                buySingal = False
                sellSingal = True
                log.info('同时满足买入和卖出条件,'+str(context.current_dt.time()))
            total = g.__dealStockDict[stockCode][1]
            counts = g.__dealStockDict[stockCode][2]
            if buySingal:
                subAmount = total - g.__operStock['b'+stockCode]
                if(subAmount > 0):
                    if(subAmount > counts):
                        order(stockCode,counts)
                        g.__operStock['b'+stockCode] = g.__operStock['b'+stockCode]+counts
                        log.info("买入股票代码为:%s, 买入 %s股" % (stockCode,counts))
                    else:
                        order(stockCode,subAmount)
                        g.__operStock['b'+stockCode] = g.__operStock['b'+stockCode]+subAmount
                        log.info("买入股票代码为:%s, 买入 %s股" % (stockCode,subAmount))
            if sellSingal:
                sumCounts = context.portfolio.positions[stockCode].closeable_amount
                if(sumCounts != 0):
                    #只能取当前可卖出股票数量
                    order_target(stockCode,0)
                    g.__operStock['s'+stockCode] = g.__operStock['s'+stockCode]+sumCounts
                    log.info('卖出股票代码为:%s,卖出股票数量为:%s'%(stockCode,sumCounts)) 
    
        #更新bma的值
        g.__bstockMaAndVol = {}    
        g.__bstockMaAndVol = changeDict
    
## 收盘后运行函数  
def after_market_close(context):
    log.info('#############################start#################################')
    log.info(str('函数运行时间(after_market_close):'+str(context.current_dt.time())))
    log.info(g.__operStock)
    g.__dealStockDict = {}
    g.__bstockMaAndVol = {}
    g.__operStock = {}
    #得到当天所有成交记录
    trades = get_trades()
    for _trade in trades.values():
        log.info('成交记录：'+str(_trade))
    log.info('一天结束')
    log.info('##############################end################################')
    
#是否具有买入信号
#1.当前bar所有ma值大于或等于与前一个bar中所有ma，ma5 > ma5',ma10 > ma10'
#2.当前bar的volnum大于前一个volnum * 3
# 参数M1=4, M2=6, M3=9, M4=13, M5=18, M6=24
def isBuySingal(context,stockCode,bstockMaAndVol,nstockMaAndVol,bma,nma,bvol,nvol):
    log.info('bstockMaAndVol:',bstockMaAndVol)
    log.info('nstockMaAndVol:',nstockMaAndVol)
    buySingal = False
    nma4 = nstockMaAndVol[nma+'4'+stockCode]
    nma6 = nstockMaAndVol[nma+'6'+stockCode]
    nma9 = nstockMaAndVol[nma+'9'+stockCode]
    nma13 = nstockMaAndVol[nma+'13'+stockCode]
    nma18 = nstockMaAndVol[nma+'18'+stockCode]
    nma24 = nstockMaAndVol[nma+'24'+stockCode]
    nvolnum = nstockMaAndVol[nvol+stockCode]
    
    bma4 = bstockMaAndVol[bma+'4'+stockCode]
    bma6 = bstockMaAndVol[bma+'6'+stockCode]
    bma9 = bstockMaAndVol[bma+'9'+stockCode]
    bma13 = bstockMaAndVol[bma+'13'+stockCode]
    bma18 = bstockMaAndVol[bma+'18'+stockCode]
    bma24 = bstockMaAndVol[bma+'24'+stockCode]
    bvolnum = bstockMaAndVol[bvol+stockCode]
    
    if nma4 > bma4 and nma6 > bma6 and nma9 > bma9 and nma13 > bma13 and nma18 > bma18 and nma24 > bma24:
        # curTime = str(context.current_dt.hour)+":"+str(context.current_dt.minute)
        # log.info('可以进行买入%s信号1层,当前时间:%s'%(stockCode,curTime))
        if nma4 > nma6 > nma9 > nma13 > nma18 :
            # log.info('可以进行买入信号2层,nvolnum:%s,bvolnum:%s'%(nvolnum,bvolnum))
            if int(nvolnum) > int(bvolnum) * 1.5 :
                buySingal = True
    return buySingal


#是否具有卖出信号
#1.如果当前价格底于nma5,nma10,nma20,nma30,nma60立刻卖出
#2.如果当前价格大于前一个bar的收盘价的3.5%,立刻全部卖出
#3.如果nma5>nma10>nma20>nma30>nma60,证明趋势还在，不做卖出判断
def isSellSingal(context,stockCode,bstockMaAndVol,nstockMaAndVol,bma,nma,bvol,nvol,minutes):
    sellSingal = False
    nma4 = nstockMaAndVol[nma+'4'+stockCode]
    nma6 = nstockMaAndVol[nma+'6'+stockCode]
    nma9 = nstockMaAndVol[nma+'9'+stockCode]
    nma13 = nstockMaAndVol[nma+'13'+stockCode]
    nma18 = nstockMaAndVol[nma+'18'+stockCode]
    nma24 = nstockMaAndVol[nma+'24'+stockCode]
    bma4 = bstockMaAndVol[bma+'4'+stockCode]
    bma6 = bstockMaAndVol[bma+'6'+stockCode]
    bma9 = bstockMaAndVol[bma+'9'+stockCode]
    bma13 = bstockMaAndVol[bma+'13'+stockCode]
    bma18 = bstockMaAndVol[bma+'18'+stockCode]
    bma24 = bstockMaAndVol[bma+'24'+stockCode]
    
    #1.如果当前时间的最新小于所有均线，产生卖出信号
    curPrice = get_current_data()[stockCode].last_price
    #取上一个bar的收盘价
    closeFm = attribute_history(stockCode, 1, str(g.__minutes)+'m', 'close')
    closePrice = closeFm['close'].mean()
    
    #1.如果当前价格大于前一个bar的收盘价的3.5%,立刻全部卖出if float(curPrice)
    if curPrice > closePrice * 1.035:
        sellSingal = True
        log.info('卖出股票代码:%s,卖出信号1'%(stockCode))
        return sellSingal
    #2.当前MA中最小的MA  
    minNma = [nma4,nma6,nma9,nma13,nma18,nma24]
    if( curPrice < min(minNma)):
        log.info('卖出股票代码:%s,卖出信号2'%(stockCode))
        sellSingal = True
        return sellSingal
    #3.如果nma5>nma10>nma20>nma30>nma60,证明趋势还在，不做卖出判断
    if nma4 > nma6 > nma9 > nma13 > nma18 > nma24:
        sellSingal = False
    else:
        if nma4 <= bma4 and nma6 <= bma6 and nma9 <= bma9 and nma13 <= bma13 and nma18 <= bma18 and nma24 <= bma24:
            # if nma5 < nma20 or nma5 < nma20 or nma5 <nma30 or nma5 < nma60:
                log.info('卖出股票代码:%s,卖出信号3'%(stockCode))
                sellSingal =True
    return sellSingal

def getStockMa(context,stockCode,count,unit,fields):
    closeStock = attribute_history(stockCode, count, str(unit)+'m', [fields])
    ma = closeStock[fields].mean()
    return formatDecimal(ma)
    # getPbxData(context,g.initStocks,'bma','bvol',g.__minutes,'close')
def getPbxData(context,dealStockDict,maHead,volHead,minutes,field):
    stockMaAndVol = {}
    for stockCode in dealStockDict.keys():
        bma4 = pbx(context,stockCode,4,minutes,field)
        bma6 = pbx(context,stockCode,6,minutes,field)
        bma9 = pbx(context,stockCode,9,minutes,field)
        bma13 = pbx(context,stockCode,13,minutes,field)
        bma18 = pbx(context,stockCode,18,minutes,field)
        bma24 = pbx(context,stockCode,24,minutes,field)
        bvol = getStockMa(context,stockCode, 1, minutes, 'volume')
        
        stockMaAndVol[maHead+'4'+stockCode] = bma4
        stockMaAndVol[maHead+'6'+stockCode] = bma6
        stockMaAndVol[maHead+'9'+stockCode] = bma9
        stockMaAndVol[maHead+'13'+stockCode] = bma13
        stockMaAndVol[maHead+'18'+stockCode] = bma18
        stockMaAndVol[maHead+'24'+stockCode] = bma24
        stockMaAndVol[volHead+stockCode] = bvol
    # log.info('stockMaAndVol:',stockMaAndVol)
    return stockMaAndVol

#此函数需要在开盘前before_market_open中执行    
#从g.initStocks中判断持仓中是否存在，如果不存在均分可用金额，进行全仓买入。
#支持exist 600570 1 持仓10000份
#    deal 600570 0 
#         600008 3 
#         600009 4
#函数返回：返回需要操作的T0股票
#stockCode:{是否持仓,持仓份数,T0操作份数},如不持仓，则有信号的时候买入T0操作份数。如果不持仓，则不用判断是否卖出。
#600570:{1,10000份,3300份}
#600008:{0,50000元,10000元}
#600009:{0,40000元,10000元}
def getStockCounts(context):
    dealStockDict = g.initStocks
    for stockCode in g.initStocks:
        sumCounts = context.portfolio.positions[stockCode].closeable_amount
        g.__operStock['b'+stockCode] = sumCounts
                #卖出0股
        g.__operStock['s'+stockCode] = 0
    return dealStockDict
    
#取消五分钟内没有完成的所有交易
def cancelOrder():
    orders = get_open_orders()
    # 循环，撤销订单
    for _order in orders.values():
        cancel_order(_order)
        
def formatDecimal(amount):
    return Decimal(amount).quantize(Decimal('.01'),rounding=ROUND_DOWN)
    
def sma_cn(X, n, m):
    return functools.reduce(lambda a, b: ((n - m) * a + m * b) / n, X)    


def pbx(context,stockCode,cycle,minutes,field):
    closeStock10 = attribute_history(stockCode, cycle, str(minutes)+'m', [field])
    X = closeStock10[field]
    s = sma_cn(X,cycle,2)
    
    ma2Stock = attribute_history(stockCode, cycle * 2, str(minutes)+'m', [field])
    ma2 = ma2Stock['close'].mean()
    
    ma4Stock = attribute_history(stockCode, cycle * 4, str(minutes)+'m', [field])
    ma4 = ma4Stock['close'].mean()
    
    ss = (s + ma2 + ma4) / 3
    
    return formatDecimal(ss)  

#初始化沪深300    
# def initHS300():
    
## 股票筛选初始化函数
def check_stocks_initialize():
    # 设定股票池
    g.security_universe = get_index_stocks('000300.XSHG')
    # 是否过滤停盘
    g.filter_paused = True
    # 是否过滤退市  
    g.filter_delisted = True
    # 是否只有ST
    g.only_st = False
    # 是否过滤ST
    g.filter_st = True    