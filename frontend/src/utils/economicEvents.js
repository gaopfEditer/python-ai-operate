/**
 * 生成经济指标日历事件
 */

// 判断是否为夏令时（3月第二个周日到11月第一个周日）
function isDaylightSavingTime(date) {
  const year = date.getFullYear();
  const month = date.getMonth();
  
  // 夏令时：3月第二个周日到11月第一个周日
  if (month < 2 || month > 10) return false; // 1月、2月、12月是冬令时
  if (month > 2 && month < 10) return true; // 4-10月是夏令时
  
  if (month === 2) { // 3月
    // 找到第二个周日
    const firstDay = new Date(year, 2, 1);
    const firstSunday = 7 - firstDay.getDay();
    const secondSunday = firstSunday + 7;
    return date.getDate() >= secondSunday;
  }
  
  if (month === 10) { // 11月
    // 找到第一个周日
    const firstDay = new Date(year, 10, 1);
    const firstSunday = 7 - firstDay.getDay();
    return date.getDate() < firstSunday;
  }
  
  return false;
}

// 美东时间转北京时间
function convertETToBJ(etDate, isDST) {
  const bjDate = new Date(etDate);
  // 美东时间到北京时间：夏令时+12小时，冬令时+13小时
  bjDate.setHours(bjDate.getHours() + (isDST ? 12 : 13));
  return bjDate;
}

// 获取某月的第N个工作日
function getNthWeekday(year, month, weekday, nth) {
  const firstDay = new Date(year, month, 1);
  const firstWeekday = firstDay.getDay();
  let daysToAdd = (weekday - firstWeekday + 7) % 7;
  if (daysToAdd === 0 && nth > 1) daysToAdd = 7;
  daysToAdd += (nth - 1) * 7;
  return new Date(year, month, 1 + daysToAdd);
}

// 获取某月的第N个指定星期几（0=周日, 1=周一, ..., 6=周六）
function getNthDayOfWeek(year, month, dayOfWeek, nth) {
  const firstDay = new Date(year, month, 1);
  const firstDayOfWeek = firstDay.getDay();
  
  // 计算到第一个目标星期几需要多少天
  let daysToFirst = (dayOfWeek - firstDayOfWeek + 7) % 7;
  
  // 如果第一天就是目标星期几，且nth=1，则daysToFirst=0
  // 如果第一天就是目标星期几，但nth>1，则需要跳到下一周
  if (daysToFirst === 0 && nth > 1) {
    daysToFirst = 7;
  }
  
  // 计算到第nth个目标星期几需要多少天
  const daysToAdd = daysToFirst + (nth - 1) * 7;
  const result = new Date(year, month, 1 + daysToAdd);
  
  // 确保结果仍在同一个月内
  if (result.getMonth() !== month) {
    // 如果超出月份，返回该月最后一个目标星期几
    const lastDay = new Date(year, month + 1, 0);
    const lastDayOfWeek = lastDay.getDay();
    let daysToLast = (lastDayOfWeek - dayOfWeek + 7) % 7;
    return new Date(year, month, lastDay.getDate() - daysToLast);
  }
  
  return result;
}

// 生成FOMC会议日期（每年8次，每6周左右，通常在1月、3月、5月等）
function generateFOMCDates(year) {
  const dates = [];
  // FOMC通常在1月、3月、5月、6月、7月、9月、11月、12月
  const months = [0, 2, 4, 5, 6, 8, 10, 11]; // 0=1月, 2=3月等
  
  months.forEach(month => {
    // 找到该月第一个周三
    const firstWednesday = getNthDayOfWeek(year, month, 3, 1);
    // FOMC通常在月中，所以找第二个或第三个周三
    const fomcDate = getNthDayOfWeek(year, month, 3, 2);
    dates.push(fomcDate);
  });
  
  return dates;
}

// 生成非农就业数据日期（每月第一个周五）
function generateNFPDates(year) {
  const dates = [];
  for (let month = 0; month < 12; month++) {
    const firstFriday = getNthDayOfWeek(year, month, 5, 1);
    dates.push(firstFriday);
  }
  return dates;
}

// 生成CPI日期（每月第2或第3个周三，通常在12-15日之间）
function generateCPIDates(year) {
  const dates = [];
  for (let month = 0; month < 12; month++) {
    // 找到该月所有周三
    const wednesdays = [];
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    
    // 找到第一个周三
    let currentDate = new Date(firstDay);
    const firstDayOfWeek = firstDay.getDay();
    let daysToFirstWed = (3 - firstDayOfWeek + 7) % 7;
    
    // 如果第一天就是周三，daysToFirstWed=0，这是第一个周三
    // 如果第一天不是周三，计算到第一个周三的天数
    if (daysToFirstWed === 0 && firstDayOfWeek !== 3) {
      daysToFirstWed = 7; // 如果计算错误，跳到下一周
    }
    
    currentDate.setDate(1 + daysToFirstWed);
    
    // 收集该月所有周三
    while (currentDate <= lastDay) {
      if (currentDate.getMonth() === month) {
        wednesdays.push(new Date(currentDate));
      }
      currentDate.setDate(currentDate.getDate() + 7);
    }
    
    // 找到在12-15日之间的周三
    let cpiDate = null;
    for (const wed of wednesdays) {
      const day = wed.getDate();
      if (day >= 12 && day <= 15) {
        cpiDate = wed;
        break;
      }
    }
    
    // 如果没有在12-15日之间的，选择最接近13.5的周三
    if (!cpiDate && wednesdays.length > 0) {
      cpiDate = wednesdays.reduce((closest, wed) => {
        const day = wed.getDate();
        const closestDay = closest.getDate();
        return Math.abs(day - 13.5) < Math.abs(closestDay - 13.5) ? wed : closest;
      });
    }
    
    dates.push(cpiDate || wednesdays[1] || wednesdays[0]); // 默认使用第二个或第一个周三
  }
  return dates;
}

// 生成PPI日期（CPI前一天，通常是周二）
function generatePPIDates(cpiDates) {
  return cpiDates.map(date => {
    const ppiDate = new Date(date);
    ppiDate.setDate(ppiDate.getDate() - 1);
    
    // 如果前一天是周末，往前找到最近的周二
    while (ppiDate.getDay() === 0 || ppiDate.getDay() === 6) {
      ppiDate.setDate(ppiDate.getDate() - 1);
    }
    
    return ppiDate;
  });
}

// 生成ISM制造业PMI日期（每月第一个工作日10:00）
function generateISMManufacturingDates(year) {
  const dates = [];
  for (let month = 0; month < 12; month++) {
    const firstDay = new Date(year, month, 1);
    let firstWorkday = firstDay;
    
    // 跳过周末
    while (firstWorkday.getDay() === 0 || firstWorkday.getDay() === 6) {
      firstWorkday = new Date(firstWorkday);
      firstWorkday.setDate(firstWorkday.getDate() + 1);
    }
    dates.push(firstWorkday);
  }
  return dates;
}

// 生成ISM非制造业PMI日期（每月第三个工作日10:00）
function generateISMNonManufacturingDates(year) {
  const dates = [];
  for (let month = 0; month < 12; month++) {
    const firstDay = new Date(year, month, 1);
    let workday = firstDay;
    let workdayCount = 0;
    
    // 找到第三个工作日
    while (workdayCount < 3) {
      if (workday.getDay() !== 0 && workday.getDay() !== 6) {
        workdayCount++;
        if (workdayCount === 3) break;
      }
      workday = new Date(workday);
      workday.setDate(workday.getDate() + 1);
    }
    dates.push(workday);
  }
  return dates;
}

// 生成零售销售日期（通常第2个周五）
function generateRetailSalesDates(year) {
  const dates = [];
  for (let month = 0; month < 12; month++) {
    const secondFriday = getNthDayOfWeek(year, month, 5, 2);
    dates.push(secondFriday);
  }
  return dates;
}

// 生成初请失业金人数日期（每周四）
function generateUnemploymentClaimsDates(year) {
  const dates = [];
  const startDate = new Date(year, 0, 1);
  const endDate = new Date(year, 11, 31);
  let currentDate = new Date(startDate);
  
  // 找到第一个周四
  while (currentDate.getDay() !== 4) {
    currentDate.setDate(currentDate.getDate() + 1);
  }
  
  while (currentDate <= endDate) {
    dates.push(new Date(currentDate));
    currentDate.setDate(currentDate.getDate() + 7);
  }
  
  return dates;
}

// 生成所有经济指标事件
export function generateEconomicEvents(year = new Date().getFullYear()) {
  const events = [];
  
  // 1. FOMC利率决议
  const fomcDates = generateFOMCDates(year);
  fomcDates.forEach(date => {
    const isDST = isDaylightSavingTime(date);
    const etTime = new Date(date);
    etTime.setHours(14, 0, 0, 0); // 美东时间14:00
    const bjTime = convertETToBJ(etTime, isDST);
    
    events.push({
      title: '美联储利率决议（FOMC）',
      start: bjTime.toISOString(),
      className: 'event-fomc',
      extendedProps: {
        type: 'FOMC',
        etTime: '14:00',
        bjTime: isDST ? '次日 02:00' : '次日 03:00',
        frequency: '每年8次',
        description: '美联储联邦公开市场委员会利率决议'
      }
    });
    
    // 鲍威尔新闻发布会（FOMC后30分钟）
    const powellTime = new Date(bjTime);
    powellTime.setMinutes(powellTime.getMinutes() + 30);
    
    events.push({
      title: '鲍威尔新闻发布会',
      start: powellTime.toISOString(),
      className: 'event-powell',
      extendedProps: {
        type: 'Powell',
        etTime: '14:30',
        bjTime: isDST ? '次日 02:30' : '次日 03:30',
        frequency: '每年8次',
        description: '美联储主席鲍威尔新闻发布会'
      }
    });
  });
  
  // 2. 非农就业数据（NFP）
  const nfpDates = generateNFPDates(year);
  nfpDates.forEach(date => {
    const isDST = isDaylightSavingTime(date);
    const etTime = new Date(date);
    etTime.setHours(8, 30, 0, 0); // 美东时间08:30
    const bjTime = convertETToBJ(etTime, isDST);
    
    events.push({
      title: '非农就业数据（NFP）',
      start: bjTime.toISOString(),
      className: 'event-nfp',
      extendedProps: {
        type: 'NFP',
        etTime: '08:30',
        bjTime: isDST ? '20:30' : '21:30',
        frequency: '每月1次',
        description: '美国非农就业数据，每月第一个周五公布'
      }
    });
  });
  
  // 3. CPI
  const cpiDates = generateCPIDates(year);
  cpiDates.forEach(date => {
    const isDST = isDaylightSavingTime(date);
    const etTime = new Date(date);
    etTime.setHours(8, 30, 0, 0); // 美东时间08:30
    const bjTime = convertETToBJ(etTime, isDST);
    
    events.push({
      title: '美国CPI（含核心CPI）',
      start: bjTime.toISOString(),
      className: 'event-cpi',
      extendedProps: {
        type: 'CPI',
        etTime: '08:30',
        bjTime: isDST ? '20:30' : '21:30',
        frequency: '每月1次',
        description: '美国消费者物价指数，通常在当月12-15日之间公布'
      }
    });
  });
  
  // 5. PPI
  const ppiDates = generatePPIDates(cpiDates);
  ppiDates.forEach(date => {
    const isDST = isDaylightSavingTime(date);
    const etTime = new Date(date);
    etTime.setHours(8, 30, 0, 0); // 美东时间08:30
    const bjTime = convertETToBJ(etTime, isDST);
    
    events.push({
      title: 'PPI（生产者物价指数）',
      start: bjTime.toISOString(),
      className: 'event-ppi',
      extendedProps: {
        type: 'PPI',
        etTime: '08:30',
        bjTime: isDST ? '20:30' : '21:30',
        frequency: '每月1次',
        description: '生产者物价指数，通常在CPI公布前一天'
      }
    });
  });
  
  // 6. ISM制造业PMI
  const ismManDates = generateISMManufacturingDates(year);
  ismManDates.forEach(date => {
    const isDST = isDaylightSavingTime(date);
    const etTime = new Date(date);
    etTime.setHours(10, 0, 0, 0); // 美东时间10:00
    const bjTime = convertETToBJ(etTime, isDST);
    
    events.push({
      title: 'ISM制造业PMI',
      start: bjTime.toISOString(),
      className: 'event-ism',
      extendedProps: {
        type: 'ISM-Manufacturing',
        etTime: '10:00',
        bjTime: isDST ? '22:00' : '23:00',
        frequency: '每月1次',
        description: 'ISM制造业采购经理人指数，每月第一个工作日公布'
      }
    });
  });
  
  // 7. ISM非制造业PMI
  const ismNonManDates = generateISMNonManufacturingDates(year);
  ismNonManDates.forEach(date => {
    const isDST = isDaylightSavingTime(date);
    const etTime = new Date(date);
    etTime.setHours(10, 0, 0, 0); // 美东时间10:00
    const bjTime = convertETToBJ(etTime, isDST);
    
    events.push({
      title: 'ISM非制造业PMI（服务业）',
      start: bjTime.toISOString(),
      className: 'event-ism',
      extendedProps: {
        type: 'ISM-NonManufacturing',
        etTime: '10:00',
        bjTime: isDST ? '22:00' : '23:00',
        frequency: '每月1次',
        description: 'ISM非制造业采购经理人指数，每月第三个工作日公布'
      }
    });
  });
  
  // 8. 零售销售
  const retailDates = generateRetailSalesDates(year);
  retailDates.forEach(date => {
    const isDST = isDaylightSavingTime(date);
    const etTime = new Date(date);
    etTime.setHours(8, 30, 0, 0); // 美东时间08:30
    const bjTime = convertETToBJ(etTime, isDST);
    
    events.push({
      title: '零售销售（Retail Sales）',
      start: bjTime.toISOString(),
      className: 'event-retail',
      extendedProps: {
        type: 'Retail',
        etTime: '08:30',
        bjTime: isDST ? '20:30' : '21:30',
        frequency: '每月1次',
        description: '美国零售销售数据，通常在第2个周五公布'
      }
    });
  });
  
  // 9. 初请失业金人数
  const unemploymentDates = generateUnemploymentClaimsDates(year);
  unemploymentDates.forEach(date => {
    const isDST = isDaylightSavingTime(date);
    const etTime = new Date(date);
    etTime.setHours(8, 30, 0, 0); // 美东时间08:30
    const bjTime = convertETToBJ(etTime, isDST);
    
    events.push({
      title: '初请失业金人数',
      start: bjTime.toISOString(),
      className: 'event-unemployment',
      extendedProps: {
        type: 'Unemployment',
        etTime: '08:30',
        bjTime: isDST ? '20:30' : '21:30',
        frequency: '每周1次',
        description: '美国初请失业金人数，每周四公布，反映前一周数据'
      }
    });
  });
  
  return events;
}

