import React, { useState, useEffect } from 'react'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import zhCnLocale from '@fullcalendar/core/locales/zh-cn'
import { getEconomicEventsFromAPI } from './utils/tradingEconomicsApi'
import { generateEconomicEvents } from './utils/economicEvents'
import './App.css'

function App() {
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear())
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [useAPI, setUseAPI] = useState(true)
  
  // 从API获取事件数据
  useEffect(() => {
    const loadEvents = async () => {
      setLoading(true)
      setError(null)
      
      try {
        if (useAPI) {
          // 尝试从API获取数据
          const apiEvents = await getEconomicEventsFromAPI(currentYear)
          
          if (apiEvents && apiEvents.length > 0) {
            setEvents(apiEvents)
            setLoading(false)
            return
          } else {
            // API没有数据，使用fallback
            console.warn('API未返回数据，使用算法计算的数据')
            setUseAPI(false)
          }
        }
        
        // 使用算法计算的数据作为fallback
        const currentYearEvents = generateEconomicEvents(currentYear)
        const nextYearEvents = generateEconomicEvents(currentYear + 1)
        setEvents([...currentYearEvents, ...nextYearEvents])
      } catch (err) {
        console.error('加载事件数据失败:', err)
        setError('加载数据失败，使用算法计算的数据')
        // 使用fallback数据
        const currentYearEvents = generateEconomicEvents(currentYear)
        const nextYearEvents = generateEconomicEvents(currentYear + 1)
        setEvents([...currentYearEvents, ...nextYearEvents])
      } finally {
        setLoading(false)
      }
    }
    
    loadEvents()
  }, [currentYear, useAPI])
  
  // 处理事件点击
  const handleEventClick = (clickInfo) => {
    const event = clickInfo.event
    const props = event.extendedProps
    const eventDate = new Date(event.start)
    
    const dateStr = `${eventDate.getFullYear()}年${eventDate.getMonth() + 1}月${eventDate.getDate()}日`
    const timeStr = `${String(eventDate.getHours()).padStart(2, '0')}:${String(eventDate.getMinutes()).padStart(2, '0')}`
    
    let message = `
${event.title}

日期: ${dateStr}
北京时间: ${timeStr}
美东时间: ${props.etTime}
公布频率: ${props.frequency}
${props.description ? `说明: ${props.description}` : ''}
    `.trim()
    
    // 如果有实际数据，显示
    if (props.actual !== null && props.actual !== undefined) {
      message += `\n\n实际值: ${props.actual}`
    }
    if (props.forecast !== null && props.forecast !== undefined) {
      message += `\n预测值: ${props.forecast}`
    }
    if (props.previous !== null && props.previous !== undefined) {
      message += `\n前值: ${props.previous}`
    }
    
    if (!useAPI || events.length === 0) {
      message += `\n\n⚠️ 注意：日期基于公布的规律计算，实际公布日期可能因节假日等因素有所调整`
    } else {
      message += `\n\n✅ 数据来源：TradingEconomics API`
    }
    
    alert(message)
  }
  
  // 处理日期导航
  const handleDatesSet = (dateInfo) => {
    const newYear = dateInfo.start.getFullYear()
    if (newYear !== currentYear) {
      setCurrentYear(newYear)
    }
  }
  
  return (
    <div className="app">
      <div className="app-header">
        <h1>📅 经济指标日历</h1>
        <p>重要经济数据发布时间一览</p>
        {loading && <p style={{ marginTop: '10px', fontSize: '14px' }}>正在加载数据...</p>}
        {error && <p style={{ marginTop: '10px', fontSize: '14px', color: '#ff6b6b' }}>{error}</p>}
        {!loading && useAPI && events.length > 0 && (
          <p style={{ marginTop: '10px', fontSize: '14px', color: '#51cf66' }}>
            ✅ 数据来源：TradingEconomics API
          </p>
        )}
        {!loading && !useAPI && (
          <p style={{ marginTop: '10px', fontSize: '14px', color: '#ffd43b' }}>
            ⚠️ 使用算法计算的数据（API未可用）
          </p>
        )}
      </div>
      
      <div className="calendar-container">
        {loading ? (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <p>正在加载日历数据...</p>
          </div>
        ) : (
          <FullCalendar
          plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
          initialView="dayGridMonth"
          headerToolbar={{
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'
          }}
          locale={zhCnLocale}
          events={events}
          eventClick={handleEventClick}
          datesSet={handleDatesSet}
          height="auto"
          eventDisplay="block"
          eventTimeFormat={{
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
          }}
          slotMinTime="00:00:00"
          slotMaxTime="24:00:00"
          allDaySlot={false}
          nowIndicator={true}
          editable={false}
          selectable={false}
          dayMaxEvents={3}
          moreLinkClick="popover"
        />
        )}
      </div>
      
      <div style={{ 
        marginTop: '20px', 
        padding: '15px', 
        background: 'white', 
        borderRadius: '10px',
        fontSize: '14px',
        color: '#666'
      }}>
        <h3 style={{ marginBottom: '10px', color: '#333' }}>📌 使用说明</h3>
        <ul style={{ lineHeight: '1.8', paddingLeft: '20px' }}>
          <li>点击日历上的事件可查看详细信息</li>
          <li>不同颜色代表不同类型的经济指标</li>
          <li>时间显示为北京时间（已自动转换夏令时/冬令时）</li>
          <li>支持月视图、周视图和日视图切换</li>
        </ul>
        {useAPI && events.length > 0 ? (
          <div style={{ marginTop: '15px', padding: '10px', background: '#d1f2eb', borderRadius: '6px', border: '1px solid #51cf66' }}>
            <strong>✅ 数据说明：</strong>日历中的日期来自 TradingEconomics API，为实际公布日期。数据每小时自动更新一次。
          </div>
        ) : (
          <div style={{ marginTop: '15px', padding: '10px', background: '#fff3cd', borderRadius: '6px', border: '1px solid #ffc107' }}>
            <strong>⚠️ 重要提示：</strong>当前使用算法计算的日期，可能与实际公布日期有差异。建议配置 TradingEconomics API 密钥以获取准确数据。请查看 README 了解如何配置。
          </div>
        )}
      </div>
    </div>
  )
}

export default App

