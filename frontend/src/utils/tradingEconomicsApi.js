/**
 * TradingEconomics API 集成
 * 用于获取准确的经济指标发布时间
 */

// API 配置 - 请将您的 API 密钥放在环境变量中
const API_KEY = import.meta.env.VITE_TRADING_ECONOMICS_API_KEY || '430ff9246d674f5:5vur2y81kfw7xyk';
const API_BASE_URL = 'https://api.tradingeconomics.com';

// 经济指标名称映射（中文 -> TradingEconomics API 中的名称）
const INDICATOR_MAPPING = {
  'FOMC': ['Federal Funds Rate', 'FOMC', 'Interest Rate Decision'],
  'NFP': ['Nonfarm Payrolls', 'Non-Farm Payrolls', 'Employment Change'],
  'CPI': ['Consumer Price Index', 'CPI', 'Inflation Rate'],
  'PPI': ['Producer Price Index', 'PPI'],
  'ISM-Manufacturing': ['ISM Manufacturing PMI', 'Manufacturing PMI'],
  'ISM-NonManufacturing': ['ISM Non-Manufacturing PMI', 'Services PMI', 'Non-Manufacturing PMI'],
  'Retail': ['Retail Sales', 'Retail Sales MoM'],
  'Unemployment': ['Initial Jobless Claims', 'Unemployment Claims'],
  'Powell': ['Fed Chair Speech', 'Powell Speech']
};

// 缓存数据（避免频繁请求）
const cache = {
  data: null,
  timestamp: null,
  ttl: 60 * 60 * 1000 // 1小时缓存
};

/**
 * 获取美国的经济指标日历数据
 */
export async function fetchUSEconomicCalendar(startDate, endDate) {
  try {
    // 检查缓存
    if (cache.data && cache.timestamp && (Date.now() - cache.timestamp) < cache.ttl) {
      return cache.data;
    }

    // 构建请求URL
    const start = startDate || new Date().toISOString().split('T')[0];
    const end = endDate || new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    
    // 使用日历端点获取数据 - 尝试多种端点格式
    let url = `${API_BASE_URL}/calendar/country/united%20states?d1=${start}&d2=${end}`;
    
    // 如果第一个端点失败，尝试其他格式
    const urls = [
      `${API_BASE_URL}/calendar/country/united%20states?d1=${start}&d2=${end}`,
      `${API_BASE_URL}/calendar?country=united%20states&d1=${start}&d2=${end}`,
      `${API_BASE_URL}/calendar/country/united%20states`
    ];
    
    let response;
    let lastError;
    
    // 尝试每个URL
    for (const testUrl of urls) {
      try {
        response = await fetch(testUrl, {
          method: 'GET',
          headers: {
            'Authorization': API_KEY,
            'Accept': 'application/json'
          }
        });
        
        if (response.ok) {
          url = testUrl;
          break;
        }
      } catch (err) {
        lastError = err;
        continue;
      }
    }
    
    if (!response || !response.ok) {
      throw new Error(`API请求失败: ${response?.status || 'Unknown'} ${response?.statusText || lastError?.message || 'Unknown error'}`);
    }

    if (!response.ok) {
      throw new Error(`API请求失败: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    
    // 更新缓存
    cache.data = data;
    cache.timestamp = Date.now();
    
    return data;
  } catch (error) {
    console.error('获取经济指标数据失败:', error);
    // 如果API失败，返回空数组，让fallback逻辑处理
    return [];
  }
}

/**
 * 根据指标类型过滤和匹配数据
 */
function matchIndicator(apiData, indicatorType) {
  const keywords = INDICATOR_MAPPING[indicatorType] || [];
  
  return apiData.filter(item => {
    const title = (item.Category || item.Event || item.Indicator || '').toLowerCase();
    const ticker = (item.Ticker || item.Symbol || '').toLowerCase();
    const country = (item.Country || '').toLowerCase();
    
    // 只匹配美国的数据
    if (country && country !== 'united states' && country !== 'us' && country !== 'united states of america') {
      return false;
    }
    
    // 检查是否匹配关键词
    return keywords.some(keyword => {
      const lowerKeyword = keyword.toLowerCase();
      return title.includes(lowerKeyword) || ticker.includes(lowerKeyword);
    });
  });
}

/**
 * 将API数据转换为日历事件格式
 */
export function convertApiDataToEvents(apiData, year) {
  const events = [];
  
  if (!apiData || apiData.length === 0) {
    return events;
  }

  // 按指标类型分组处理
  Object.keys(INDICATOR_MAPPING).forEach(indicatorType => {
    const matchedData = matchIndicator(apiData, indicatorType);
    
    matchedData.forEach(item => {
      try {
        // 解析日期时间 - 尝试多种日期字段
        let eventDate;
        const dateFields = ['Date', 'DateTime', 'ReleaseDate', 'EventDate', 'Time'];
        for (const field of dateFields) {
          if (item[field]) {
            eventDate = new Date(item[field]);
            if (!isNaN(eventDate.getTime())) {
              break;
            }
          }
        }
        
        if (!eventDate || isNaN(eventDate.getTime())) {
          return; // 跳过无效日期
        }

        // 只处理指定年份的数据
        if (eventDate.getFullYear() !== year && eventDate.getFullYear() !== year + 1) {
          return;
        }

        // 确定事件标题和类型
        let title = item.Category || item.Event || item.Indicator || item.Ticker || '经济指标';
        let className = `event-${indicatorType.toLowerCase()}`;
        
        // 特殊处理
        if (indicatorType === 'FOMC') {
          title = '美联储利率决议（FOMC）';
          className = 'event-fomc';
        } else if (indicatorType === 'NFP') {
          title = '非农就业数据（NFP）';
          className = 'event-nfp';
        } else if (indicatorType === 'CPI') {
          title = '美国CPI（含核心CPI）';
          className = 'event-cpi';
        } else if (indicatorType === 'PPI') {
          title = 'PPI（生产者物价指数）';
          className = 'event-ppi';
        } else if (indicatorType === 'ISM-Manufacturing') {
          title = 'ISM制造业PMI';
          className = 'event-ism';
        } else if (indicatorType === 'ISM-NonManufacturing') {
          title = 'ISM非制造业PMI（服务业）';
          className = 'event-ism';
        } else if (indicatorType === 'Retail') {
          title = '零售销售（Retail Sales）';
          className = 'event-retail';
        } else if (indicatorType === 'Unemployment') {
          title = '初请失业金人数';
          className = 'event-unemployment';
        }

        // 获取时间信息
        const etTime = eventDate;
        const isDST = isDaylightSavingTime(etTime);
        const bjTime = convertETToBJ(new Date(etTime), isDST);

        // 构建事件对象
        events.push({
          title: title,
          start: bjTime.toISOString(),
          className: className,
          extendedProps: {
            type: indicatorType,
            etTime: etTime.toLocaleTimeString('en-US', { 
              hour: '2-digit', 
              minute: '2-digit',
              hour12: false,
              timeZone: 'America/New_York'
            }),
            bjTime: bjTime.toLocaleTimeString('zh-CN', { 
              hour: '2-digit', 
              minute: '2-digit',
              hour12: false
            }),
            frequency: item.Frequency || item.Period || '每月1次',
            description: item.Category || item.Event || item.Indicator || '',
            actual: item.Actual || item.Value || null,
            forecast: item.Forecast || item.Expected || null,
            previous: item.Previous || item.LastValue || null
          }
        });
      } catch (error) {
        console.warn('处理事件数据时出错:', error, item);
      }
    });
  });

  return events;
}

/**
 * 判断是否为夏令时
 */
function isDaylightSavingTime(date) {
  const year = date.getFullYear();
  const month = date.getMonth();
  
  if (month < 2 || month > 10) return false;
  if (month > 2 && month < 10) return true;
  
  if (month === 2) {
    const firstDay = new Date(year, 2, 1);
    const firstSunday = 7 - firstDay.getDay();
    const secondSunday = firstSunday + 7;
    return date.getDate() >= secondSunday;
  }
  
  if (month === 10) {
    const firstDay = new Date(year, 10, 1);
    const firstSunday = 7 - firstDay.getDay();
    return date.getDate() < firstSunday;
  }
  
  return false;
}

/**
 * 美东时间转北京时间
 */
function convertETToBJ(etDate, isDST) {
  const bjDate = new Date(etDate);
  bjDate.setHours(bjDate.getHours() + (isDST ? 12 : 13));
  return bjDate;
}

/**
 * 获取经济指标事件（使用API数据）
 */
export async function getEconomicEventsFromAPI(year = new Date().getFullYear()) {
  try {
    const startDate = `${year}-01-01`;
    const endDate = `${year + 1}-12-31`;
    
    const apiData = await fetchUSEconomicCalendar(startDate, endDate);
    const events = convertApiDataToEvents(apiData, year);
    
    return events;
  } catch (error) {
    console.error('获取API事件失败:', error);
    return [];
  }
}

