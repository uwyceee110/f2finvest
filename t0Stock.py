#coding= utf-8
# 导入函数库
import functools
import sys
import time
from decimal import *
import jqdata
import numpy as np
import pandas as pd
import talib as tl
from operator import methodcaller


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

    #存取上一个bar的ma5,ma10,ma20,ma30,ma60。每次开盘前重新初始化
    g.bstockMaAndVol = {}
    
    g.nstockMaAndVol = {}
    
    #T0的分钟数
    g.minutes = 15
    
    #上一个bar数据open ,close
    g.stockPerBarArray={}

    #当日持仓，每日需要清仓
    g.curPostions=[]

    #单只股盈利过多少进行卖出操作
    g.profitUpRatio = 10

    #单只股票买入仓位
    g.positionRate = 0.1

    #个股买入金额
    g.singleStocksAmt = 0

    #当日选股函数集
    g.curDayStocks = 0
    
    #大盘买入卖出标识
    g.CDLFuncList = [
        'CDLXSIDEGAP3METHODS'
        ]
    
    g.isClear = False

    '''g.initPosition初始化选股和持仓
    dict数据：
    key：股票代码 
    values: [每次买入股票数量,底仓数量,最高持仓数量]
    '''
    g.initPosition= {'600570.XSHG':[2000,2000,6000],'600196.XSHG':[2000,2000,6000]}

    g.dealTimes = 0

    #当日买入股票的时间
    g.curDayBuyStocks = {}

##当天的每日持仓
def getCurDayPosition(context):
    g.curPostions = context.portfolio.positions.keys()
    
## 开盘前运行函数                                                                                                                                                                           
def before_market_open(context):
    #获取当日持仓
    getCurDayPosition(context)
    #计算个股金额
    g.singleStocksAmt = context.portfolio.inout_cash * g.positionRate

    for stockCode in g.curPostions:
        #存取上一个bar的ma5,ma10,ma20,ma30,ma60。每次开盘前重新初始化(context,dealStockDict,maHead,volHead,minutes,field):
        nstockMaAndVol,stockBarArray = getPbxData(context,stockCode,'nma','nvol',g.minutes,'close')
        g.nstockMaAndVol.update(nstockMaAndVol)
        g.stockPerBarArray[stockCode] = stockBarArray

        bstockMaAndVol = nstock2bstockMaAndVol(g.nstockMaAndVol,stockCode,'nma','nvol','bma','bvol')
        g.bstockMaAndVol.update(bstockMaAndVol)

    #每日开盘进行选股10到100支
    ##a.选股函数进行选股
    g.curDayStocks = selectStocks(context)
    for selectStock in g.curDayStocks:
        nstockMaAndVol,stockBarArray = getPbxData(context,selectStock,'nma','nvol',g.minutes,'close')
        g.nstockMaAndVol.update(nstockMaAndVol)
        g.stockPerBarArray[selectStock] = stockBarArray
    
        bstockMaAndVol = nstock2bstockMaAndVol(g.nstockMaAndVol,selectStock,'nma','nvol','bma','bvol')
        g.bstockMaAndVol.update(bstockMaAndVol)
        
    #是否大盘清仓
    g.isClear = isClearAllStocks(context)
    log.info(' isClear:',g.isClear)
    
## 开盘时运行函数
def market_open(context):
    runMinute = context.current_dt.minute
    runHour = context.current_dt.hour
    passMinute = str(runHour)+':'+str(runMinute)
    
    if passMinute == '9:30' or passMinute == '14:55' or passMinute == '15:00':
        #恢复持仓
        # if passMinute == '14:55':
        #     resetPostions(context)
        return False

    dealMinute = context.current_dt.minute
    #取前5分钟的BAR,当前的分钟与前面的bar还有瀑布线的ma4,ma6,ma9进行比较。提高准确性，所以程序可以每分钟进行交易，进行买入和卖出
    if int(dealMinute) % g.minutes == 0:
        g.dealTimes += 1

        for stockCode in g.curPostions:
            # log.info('函数运行时间(market_open):'+str(context.current_dt.time()))
            bstockMaAndVol = nstock2bstockMaAndVol(g.nstockMaAndVol,stockCode,'nma','nvol','bma','bvol')
            g.bstockMaAndVol.update(bstockMaAndVol)
            nstockMaAndVol,stockBarArray = getPbxData(context,stockCode,'nma','nvol',g.minutes,'close')
            g.nstockMaAndVol.update(nstockMaAndVol)
            g.stockPerBarArray[stockCode] = stockBarArray

        for selectCode in g.curDayStocks:
            bstockMaAndVol = nstock2bstockMaAndVol(g.nstockMaAndVol,selectCode,'nma','nvol','bma','bvol')
            g.bstockMaAndVol.update(bstockMaAndVol)
            nstockMaAndVol,stockBarArray = getPbxData(context,selectCode,'nma','nvol',g.minutes,'close')
            g.nstockMaAndVol.update(nstockMaAndVol)
            g.stockPerBarArray[selectCode] = stockBarArray
    #是否大盘清仓
    if(g.isClear):
        clearAllStocks(context)
    else:
        #a.对已有持仓进行操作
        for stockCode in g.curPostions:
            closeAmt = 0
            if(context.portfolio.positions.has_key(stockCode)):
                closeAmt = context.portfolio.positions[stockCode].closeable_amount
            eachAmt = g.initPosition[stockCode][0]
            '''单只持股是否减仓
            1.有可用持仓
            2.可用持仓大于单次操作持仓
            '''
            if(closeAmt >= eachAmt):
                isSale = checkSaleStock(context,stockCode)      
                if(isSale):
                    #当前持仓-单次操作数量>0进行卖出
                    avgCost = context.portfolio.positions[stockCode].avg_cost
                    curPrice = context.portfolio.positions[stockCode].price
                    curPrice1 = curPrice* 1.006
                    curPrice2 = curPrice* 0.994
                    if(avgCost < curPrice2 or avgCost > curPrice1):
                        order_target(stockCode, 0)

        #判断是否加仓
        for mCode in g.initPosition.keys():
            flag = False
            if mCode not in g.curDayBuyStocks:
                flag = True
            else:
                stockDealTime = g.curDayBuyStocks[mCode]
                if stockDealTime != g.dealTimes:
                    flag = True
            if(flag):
                culAmt = 0
                if(context.portfolio.positions.has_key(mCode)):
                    culAmt = context.portfolio.positions[mCode].total_amount
                eachAmt = g.initPosition[mCode][0]
                totalAmt = g.initPosition[mCode][2]
                if(totalAmt > culAmt):
                    buySingal = isBuySingal(context,mCode,g.bstockMaAndVol,g.nstockMaAndVol,'bma','nma','bvol','nvol')
                    if buySingal:
                        order_target(mCode, min(culAmt+eachAmt,totalAmt))
                        g.curDayBuyStocks[mCode] = g.dealTimes
        
## 收盘后运行函数  
def after_market_close(context):
    log.info('#############################start#################################')
    g.bstockMaAndVol = {}
    g.nstockMaAndVol = {}
    g.stockBarArray = {}
    g.curPostions = {}
    g.curDayBuyStocks = {}
    #得到当天所有成交记录
    orders = get_orders()
    for _order in orders.values():
        log.info("order stockCode is :%s, amount: %s, flag: %s" % (_order.security,_order.filled,_order.action))
    log.info('##############################end################################')

def resetPostions(context):
    for stock in g.initPosition:
        order_target(stock, g.initPosition[stock][1])

#技术确认买入操作
def buyStockByAnalysis(context,valStocks,singleStocksAmt):
    for stockCode in valStocks:
        if stockCode not in g.curDayBuyStocks and stockCode not in g.curPostions:
            buySingal = isBuySingal(context,stockCode,g.bstockMaAndVol,g.nstockMaAndVol,'bma','nma','bvol','nvol')
            if buySingal:
                order_value(stockCode, singleStocksAmt)
                g.curDayBuyStocks.append(stockCode)
                # log.info("By stockCode is :%s, amount: %s" % (stockCode,singleStocksAmt))
    
#是否具有T0买入信号
#1.当前bar所有ma值大于或等于与前一个bar中所有ma，ma5 > ma5',ma10 > ma10'
#2.当前bar的volnum大于前一个volnum * 3
# 参数M1=4, M2=6, M3=9, M4=13, M5=18, M6=24
def isBuySingal(context,stockCode,bstockMaAndVol,nstockMaAndVol,bma,nma,bvol,nvol):
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
    
    curPrice = get_current_data()[stockCode].last_price
    maList = [curPrice,nma4,nma6,nma9,nma13,nma18,nma24]
    maMax = max(maList)
    maMin = min(maList)
 
    if(int(maMax) < int(maMin) * 1.003):
        return False
    
    if nma4 > bma4 and nma6 > bma6 and nma9 > bma9 and nma13 > bma13 and nma18 >= bma18 and nma24 >= bma24:
        # curTime = str(context.current_dt.hour)+":"+str(context.current_dt.minute)
        # log.info('可以进行买入%s信号1层,当前时间:%s'%(stockCode,curTime))
        if nma4 > nma6 > nma9 > nma13 > nma18 :
            # log.info('可以进行买入信号2层,nvolnum:%s,bvolnum:%s'%(nvolnum,bvolnum))
            if int(nvolnum) > int(bvolnum) * 1.5 :
                # log.info('满足均线条件的买入！！！')
                return True
            
    # 如果放量下跌，超过3倍的成交量。当前价格在ma下面，当前价格比close价高。
    nAarray = g.stockPerBarArray[stockCode]
    barClose = nAarray['close']
    barOpen = nAarray['open']
    
    if(nma4 < nma6 < nma9 < nma13 < nma18 < nma24 and barOpen > barClose):
        if(int(nvolnum) > int(bvolnum) * 3 and curPrice > nma4):
            return True
            
    #突然放量上涨
    # if(int(nvolnum) > int(bvolnum) * 3 and curPrice >= maMax):
    #     return True

#是否具有T0卖出信号
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
    
    maList = [nma4,nma6,nma9,nma13,nma18,nma24]
    maMax = max(maList)
    maMin = min(maList)

    if(int(maMax) < int(maMin) * 1.003 ):
        return False
    
    #1.如果当前时间的最新小于所有均线，产生卖出信号
    curPrice = get_current_data()[stockCode].last_price
    #取上一个bar的收盘价
    nAarray = g.stockPerBarArray[stockCode]
    barClose = nAarray['close']
    
    #1.如果当前价格大于前一个bar的收盘价的3.5%,立刻全部卖出if float(curPrice)
    # if curPrice > closePrice * 1.035:
    #     sellSingal = True
    #     return sellSingal
    #3.如果nma5>nma10>nma20>nma30>nma60,证明趋势还在，不做卖出判断
    if nma4 < nma9 and barClose < nma4:
        sellSingal =True
        return sellSingal
    #2.当前MA中最小的MA  
    minNma = [nma4,nma6,nma9,nma13,nma18,nma24]
    if( curPrice < min(minNma)):
        # log.info('sell stock:%s,sell single is 2'%(stockCode))
        sellSingal = True
        return sellSingal
    return sellSingal
    
    #取ma中min，max，如果在0.2波动，不进行操作

def getStockMa(context,stockCode,count,unit,fields):
    closeStock = attribute_history(stockCode, count, str(unit)+'m', [fields])
    ma = closeStock[fields].mean()
    return formatDecimal(ma)
    
def getPbxData(context,stockCode,maHead,volHead,minutes,field):
    stockMaAndVol = {}
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

    stockBarArray = get_bars(stockCode, 1, unit=str(g.minutes)+'m',fields=['open','close'],include_now=True)
    # log.info('stock:%s,stockBarArray:%s'%(stockCode,stockBarArray))
    return stockMaAndVol,stockBarArray

def nstock2bstockMaAndVol(nstockMaAndVol,stockCode,nma,nvol,bma,bvol):
    bstockMaAndVol = {}
    bstockMaAndVol[bma+'4'+stockCode] = nstockMaAndVol[nma+'4'+stockCode]
    bstockMaAndVol[bma+'6'+stockCode] = nstockMaAndVol[nma+'6'+stockCode]
    bstockMaAndVol[bma+'9'+stockCode] = nstockMaAndVol[nma+'9'+stockCode]
    bstockMaAndVol[bma+'13'+stockCode] = nstockMaAndVol[nma+'13'+stockCode]
    bstockMaAndVol[bma+'18'+stockCode] = nstockMaAndVol[nma+'18'+stockCode]
    bstockMaAndVol[bma+'24'+stockCode] = nstockMaAndVol[nma+'24'+stockCode]
    bstockMaAndVol[bvol+stockCode] = nstockMaAndVol[nvol+stockCode]
    return bstockMaAndVol
        
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

def paused_filter(security_list):
    current_data = get_current_data()
    security_list = [stock for stock in security_list if not current_data[stock].paused]
    return security_list

def pick(context):
        # 获取当前时间
        date=context.current_dt.strftime("%Y-%m-%d")
        # 获取上证指数和深证综指的成分股代码并连接，即为全A股市场所有股票
        scu = get_index_stocks('000001.XSHG')+get_index_stocks('399106.XSHE')
        
        
        scu = paused_filter(scu)
        # scu = high_limit_filter(context,scu)
        #scu = filter_n_tradeday_not_buy(scu, 10)
        
        df = get_fundamentals(query(
                valuation.code,
                valuation.market_cap,
                valuation.pe_ratio,
                valuation.pb_ratio,
                indicator.inc_net_profit_year_on_year,
                indicator.inc_return
            ).filter(
                (valuation.code.in_(scu))&
                (valuation.market_cap>50)&
                (valuation.pe_ratio<22)&
                (valuation.pe_ratio>0)&
                (valuation.pe_ratio/indicator.inc_net_profit_year_on_year<1.1)&
                (valuation.pe_ratio/indicator.inc_net_profit_year_on_year>0)
            ).order_by(
                indicator.inc_return.desc()
            ), date=date
            )

        # 取出前g.stocksnum名的股票代码，并转成list类型，buylist为选中的股票
        buylist =list(df['code'][:20])
        
        return buylist

#选股函数
def selectStocks(context):
    # valStocks = ['600570.XSHG','600571.XSHG','600196.XSHG']
    # valStocks  =  get_index_stocks('000300.XSHG')
    # valStocks = pick(context)
    valStocks = g.initPosition.keys()
    return valStocks

 #大盘是否清仓   
def isClearAllStocks(context):
    try:
        rs = False
        hData = attribute_history('000001.XSHG', 40, unit='1d'
                    , fields=('close', 'volume', 'open', 'high', 'low')
                    , skip_paused=False
                    , df=False)
        volume = hData['volume']
        close = hData['close']
        openp = hData['open']
        high = hData['high']
        low = hData['low']
        i = talib.CDL2CROWS(openp,high,low,close)
        rs = i[-1] == -100
    except expression as identifier:
        pass
    finally:
        return rs

def clearAllStocks(context):
    for stock in context.portfolio.positions.keys():
        order_target_value(stock, 0) 

#个股是否清仓:
#清仓条件1.个股赢利过5%。2.亏损过3% 3.T0卖出信号
def checkSaleStock(context,stockCode):
    # saleFlag = upStopProfit(context,stockCode)
    # if(saleFlag):
    #     return saleFlag
    # saleFlag = downStopProfit(context,stockCode)    
    # if(saleFlag):
    #     return saleFlag
    saleFlag = isSellSingal(context,stockCode,g.bstockMaAndVol,g.nstockMaAndVol,'bma','nma','bvol','nvol',g.minutes)        
    if(saleFlag):
        return saleFlag

#个股止赢
def upStopProfit(context,stockCode,profit=0.5):
    avg_cost = 0
    current_price = 0
    if(context.portfolio.positions.has_key(stockCode)):
        avg_cost = context.portfolio.positions[stockCode].avg_cost
        current_price = context.portfolio.positions[stockCode].price
    if avg_cost != 0 and current_price/avg_cost - 1 >= profit:
        # log.info(str(stockCode) + '  stock up ,stop profit!')
        return True       
        # order_target_value(stock, 0)
    else:
        return False

#个股止损
def downStopProfit(context,stockCode,profit=0.3):
    avg_cost = 0
    current_price = 0
    if(context.portfolio.positions.has_key(stockCode)):
        avg_cost = context.portfolio.positions[stockCode].avg_cost
        current_price = context.portfolio.positions[stockCode].price
    if avg_cost != 0 and 1 - current_price/avg_cost>= profit:
        # log.info(str(stockCode) + '  stock down ,stop profit!')
        return True
    else:
        return False
        # order_target_value(stock, 0)


if __name__ == '__main__':
    import jqsdk
    params = {
    'token':'261ffd187836a3d8469499aeb45c32c7',
    'algorithmId':6,
    'baseCapital':300000,
    'frequency':'minute',
    'startTime':'2018-01-01',
    'endTime':'2018-10-01',
    'name':"Test1",
    }
    jqsdk.run(params)
