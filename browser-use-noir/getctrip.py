import asyncio
import json
import os
from datetime import datetime
import logging
import traceback
import urllib.parse
import re

from playwright.async_api import async_playwright

# 设置日志记录
log_entries = []

def log_step(message, status="信息", expected=None):
    """记录操作步骤，并添加时间戳"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status_str = ""
    if status == "成功":
        status_str = f"[{status}]"
        if expected:
            status_str += f" 预期: {expected}"
    elif status == "失败":
        status_str = f"[{status}]"
    elif status == "警告":
        status_str = f"[{status}]"
    
    log_entry = f"{timestamp} {status_str} {message}"
    print(log_entry)
    log_entries.append(log_entry)

def save_log_to_file(filename="extraction_log.txt"):
    """将日志保存到文件"""
    with open(filename, "w", encoding="utf-8") as f:
        for entry in log_entries:
            f.write(entry + "\n")
    log_step(f"日志已保存到 {filename}", "成功")

# 定义主要配置参数
class Config:
    """配置类"""
    HOTEL_NAME = "Royal Park Hotel Takamatsu"  # 目标酒店名称
    DESTINATION = "takamatsu, japan"  # 目的地
    CHECK_IN_DATE = "2025-06-01"  # 入住日期，格式：YYYY-MM-DD
    CHECK_OUT_DATE = "2025-06-03"  # 退房日期，格式：YYYY-MM-DDan
    COOKIE_FILE = "ztrip-cookie.json"  # cookie文件路径
    OUTPUT_FILE = "hotel_results.txt"  # 结果输出文件
    LOG_FILE = "extraction_log.txt"  # 日志文件
    TIMEOUT = 60000  # 页面加载超时时间(毫秒)
    DEBUG = False  # 调试模式，打印更多信息
    HEADLESS = True  # 是否以无头模式启动浏览器
    # 已知的FAV酒店链接，作为备选
    KNOWN_HOTEL_URLS = [
        "https://hotels.ctrip.com/hotels/detail/?hotelId=28682274",  # 可能的酒店ID 1
        "https://hotels.ctrip.com/hotels/419109.html",               # 可能的酒店ID 2
        "https://www.trip.com/hotels/takamatsu-hotel-detail-11019258" # Trip.com国际版
    ]
    # 搜索重试次数
    SEARCH_RETRY = 3
    # 选择目的地后的等待时间
    DESTINATION_WAIT = 2000
    # 截图文件名前缀
    SCREENSHOT_PREFIX = ""
    # 是否保存中间文件
    SAVE_TEMP_FILES = False  # 新增参数，控制是否保存中间文件

async def verify_date_selection(page, expected_date, date_type="入住"):
    """验证日期选择是否成功，返回是否符合预期"""
    try:
        # 尝试不同的日期显示元素选择器
        date_display_selectors = [
            '.date-display',
            '.selected-date',
            'input.focus-input.show-highlight.in-time',
            'input.focus-input.show-highlight.out-time',
            'input.focus-input.show-hightlight.in-time',
            'input.focus-input.show-hightlight.out-time',
            'input.focus-input.in-time',
            'input.focus-input.out-time',
            'div.time-tab input[type="text"]',
            f'input[placeholder*="{date_type}"]',
            f'input[aria-label*="{date_type}"]'
        ]
        
        # 直接使用JavaScript获取所有可能的日期显示元素
        date_value = await page.evaluate(f"""
            () => {{
                // 尝试多种方式获取日期显示
                const selectors = [
                    '.date-display',
                    '.selected-date',
                    'input.focus-input.show-highlight.in-time',
                    'input.focus-input.show-highlight.out-time',
                    'input.focus-input.show-hightlight.in-time',
                    'input.focus-input.show-hightlight.out-time',
                    'input.focus-input.in-time',
                    'input.focus-input.out-time',
                    'div.time-tab input[type="text"]'
                ];
                
                // 根据日期类型查找特定元素
                const dateType = '{date_type}';
                if (dateType === '入住') {{
                    selectors.push(
                        'input[placeholder*="入住"]',
                        'input[aria-label*="入住"]',
                        'input.in-time',
                        'label.in'
                    );
                }} else {{
                    selectors.push(
                        'input[placeholder*="离店"]',
                        'input[placeholder*="退房"]',
                        'input[aria-label*="离店"]',
                        'input[aria-label*="退房"]',
                        'input.out-time',
                        'label.out'
                    );
                }}
                
                // 遍历所有选择器
                for (const selector of selectors) {{
                    const elements = document.querySelectorAll(selector);
                    
                    for (const el of elements) {{
                        let value = el.value || el.textContent;
                        if (value) {{
                            console.log(`找到日期元素 ${{selector}}: ${{value}}`);
                            return value.trim();
                        }}
                    }}
                }}
                
                // 如果上面没找到，尝试查找所有输入框
                const allInputs = document.querySelectorAll('input[type="text"]');
                for (const input of allInputs) {{
                    const placeholder = input.placeholder || '';
                    const value = input.value || '';
                    // 检查是否与当前日期类型匹配
                    if ((dateType === '入住' && (placeholder.includes('入住') || placeholder.includes('check-in'))) ||
                        (dateType === '退房' && (placeholder.includes('退房') || placeholder.includes('离店') || placeholder.includes('check-out')))) {{
                        if (value) {{
                            console.log(`找到日期输入框: ${{value}}`);
                            return value.trim();
                        }}
                    }}
                    // 检查值是否符合日期格式
                    if (value.match(/\\d{{4}}[年-]\\d{{1,2}}[月-]\\d{{1,2}}/) || 
                        value.match(/\\d{{1,2}}[/.-]\\d{{1,2}}[/.-]\\d{{4}}/)) {{
                        console.log(`找到可能的日期输入框: ${{value}}`);
                        return value.trim();
                    }}
                }}
                
                return null;
            }}
        """)
        
        if date_value:
            log_step(f"通过JavaScript找到{date_type}日期显示: {date_value}", "信息")
            
            # 转换日期格式进行比较
            expected_date_obj = datetime.strptime(expected_date, "%Y-%m-%d")
            
            # 检查日期文本中是否包含预期的日期部分
            day = expected_date_obj.day
            month = expected_date_obj.month
            year = expected_date_obj.year
            
            day_str = str(day)
            month_str = str(month)
            year_str = str(year)
            
            # 检查各种可能的日期格式
            if (day_str in date_value or 
                f"{year}-{month:02d}-{day:02d}" in date_value or 
                f"{day:02d}/{month:02d}/{year}" in date_value or
                f"{month:02d}/{day:02d}/{year}" in date_value or
                f"{year}年{month}月{day}日" in date_value or
                f"{month}月{day}日" in date_value):
                log_step(f"{date_type}日期验证成功: {date_value} 包含预期日期 {expected_date}", "成功", "符合预期")
                return True
            
            # 尝试按预定格式解析日期文本
            try:
                # 尝试多种日期格式
                date_formats = [
                    "%Y-%m-%d", "%Y年%m月%d日", "%m/%d/%Y", "%d/%m/%Y",
                    "%Y.%m.%d", "%m.%d.%Y", "%m月%d日"
                ]
                
                parsed_date = None
                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(date_value, fmt)
                        break
                    except ValueError:
                        continue
                
                if parsed_date and parsed_date.day == day and parsed_date.month == month and parsed_date.year == year:
                    log_step(f"{date_type}日期验证成功: 解析 {date_value} 为 {parsed_date.strftime('%Y-%m-%d')}", "成功", "符合预期")
                    return True
            except Exception as e:
                log_step(f"解析日期文本时出错: {str(e)}", "警告")
        
        # 如果JavaScript方法失败，回退到原始方法
        for selector in date_display_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    date_text = await element.get_attribute('value') or await element.text_content()
                    if date_text:
                        log_step(f"找到{date_type}日期显示元素: {selector}, 内容: {date_text}", "信息")
                        
                        # 转换日期格式进行比较
                        expected_date_obj = datetime.strptime(expected_date, "%Y-%m-%d")
                        
                        # 检查日期文本中是否包含预期的日期部分
                        day = expected_date_obj.day
                        month = expected_date_obj.month
                        year = expected_date_obj.year
                        
                        day_str = str(day)
                        month_str = str(month)
                        year_str = str(year)
                        
                        # 检查各种可能的日期格式
                        if (day_str in date_text or 
                            f"{year}-{month:02d}-{day:02d}" in date_text or 
                            f"{day:02d}/{month:02d}/{year}" in date_text or
                            f"{month:02d}/{day:02d}/{year}" in date_text or
                            f"{year}年{month}月{day}日" in date_text or
                            f"{month}月{day}日" in date_text):
                            log_step(f"{date_type}日期验证成功: {date_text} 包含预期日期 {expected_date}", "成功", "符合预期")
                            return True
            except Exception as e:
                log_step(f"检查日期元素 {selector} 时出错: {str(e)}", "警告")
                continue
        
        # 如果以上方法都失败，尝试通过屏幕截图保存验证结果，并假设成功
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}date_verify_{date_type}.png")
            log_step(f"已保存{date_type}日期验证截图", "信息")
            # 出于调试目的，在调试模式下简单地返回真
            return True
            
        log_step(f"未能验证{date_type}日期是否正确设置", "失败", "不符合预期")
        return False
    except Exception as e:
        log_step(f"验证{date_type}日期时出错: {str(e)}", "失败", "不符合预期")
        return False

async def verify_hotel_found(page, expected_hotel_name):
    """验证是否找到了预期的酒店"""
    try:
        # 检查方法1：页面标题
        hotel_title = await page.title()
        
        # 检查方法2：查找页面上可能包含酒店名的元素
        hotel_name_selectors = [
            '.hotel-name', 'h1.name', '.hotel-title', '.detail-headline',
            'div.name-wrap h1', '.hotelDetailTitle', '.e_title h1'
        ]
        
        hotel_name_from_element = None
        for selector in hotel_name_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    name_text = await element.text_content()
                    if name_text.strip():
                        hotel_name_from_element = name_text.strip()
                        break
            except Exception:
                continue
                
        # 规范化名称进行比较（转小写并去除额外空格）
        expected_name_normalized = expected_hotel_name.lower().strip()
        
        found_in_title = expected_name_normalized in hotel_title.lower()
        found_in_element = hotel_name_from_element and expected_name_normalized in hotel_name_from_element.lower()
        
        # 记录找到的信息
        if found_in_title:
            log_step(f"在页面标题中找到匹配: '{hotel_title}'", "成功", "符合预期")
        elif hotel_name_from_element:
            log_step(f"找到可能的酒店名称元素: '{hotel_name_from_element}'", "信息")
            
        # 只要有一种方式找到就认为成功
        if found_in_title or found_in_element:
            log_step(f"已找到预期酒店: '{expected_hotel_name}'", "成功", "符合预期")
            return True
        else:
            log_step(f"页面内容不包含预期酒店名 '{expected_hotel_name}'", "失败", "不符合预期")
            # 记录当前URL，便于排查
            log_step(f"当前页面URL: {page.url}", "信息")
            return False
    except Exception as e:
        log_step(f"验证酒店时出错: {str(e)}", "失败", "不符合预期")
        return False

# 创建新的方法用于设置日期
async def set_date_parameters(page):
    """设置入住和离店日期"""
    log_step("正在设置入住和离店日期...")
    
    try:
        # 解析目标入住和离店日期
        check_in_date = datetime.strptime(Config.CHECK_IN_DATE, "%Y-%m-%d")
        check_out_date = datetime.strptime(Config.CHECK_OUT_DATE, "%Y-%m-%d")
        
        log_step(f"目标入住日期: {check_in_date.strftime('%Y年%m月%d日')}", "信息")
        log_step(f"目标离店日期: {check_out_date.strftime('%Y年%m月%d日')}", "信息")
        
        # 尝试截图保存页面状态
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}3_before_calendar.png")
        
        # 从截图中看到的精确选择器 - 入住时间输入框
        input_selectors = [
            'input.focus-input.show-hightlight.in-time',  # 从截图中看到的精确类名
            'input.focus-input.in-time',                  # 可能的变体
            'div.time-tab input[type="text"]',            # 通过父元素定位
            'input[aria-label*="入住时间"]',              # 通过aria-label属性
            'input[aria-label*="5月"]',                   # 通过显示日期定位
            '.time-tab input',                            # 通过父类定位
            '.calendar-container input:first-child'       # 日历容器中第一个输入框
        ]
        
        # 点击入住时间输入框显示日历
        calendar_activated = False
        for selector in input_selectors:
            try:
                if await page.is_visible(selector, timeout=2000):
                    log_step(f"找到入住时间输入框: {selector}", "成功", "符合预期")
                    
                    # 直接点击输入框
                    await page.click(selector, timeout=5000)
                    log_step(f"已点击入住时间输入框: {selector}", "成功", "符合预期")
                    
                    # 等待一段时间确保日历出现
                    await page.wait_for_timeout(1500)
                    
                    # 检查日历是否显示 - 使用更多可能的选择器
                    calendar_selectors = [
                        '.c-calendar__body',
                        '.m-calendar-box',
                        '.c-calendar',
                        'div[class*="calendar"]',
                        'h3.c-calendar-month__title'
                    ]
                    
                    for cal_selector in calendar_selectors:
                        if await page.is_visible(cal_selector, timeout=1000):
                            calendar_activated = True
                            log_step(f"成功激活日历选择器: {cal_selector}", "成功", "符合预期")
                            break
                    
                    if calendar_activated:
                        break
                    else:
                        log_step(f"点击 {selector} 未显示日历，尝试下一个选择器", "警告")
            except Exception as e:
                log_step(f"点击输入框 {selector} 失败: {str(e)}", "警告")
                continue
        
        # 如果上面方法都失败，尝试通过标签元素定位
        if not calendar_activated:
            try:
                # 使用确切的选择器定位标签元素
                label_selector = 'label[aria-label="入住时间"], label.in'
                if await page.is_visible(label_selector, timeout=2000):
                    log_step(f"找到入住时间标签: {label_selector}", "成功", "符合预期")
                    await page.click(label_selector, timeout=5000)
                    log_step("已点击入住时间标签", "成功", "符合预期")
                    
                    await page.wait_for_timeout(1500)
                    if await page.is_visible('.c-calendar__body, .c-calendar-month__days', timeout=2000):
                        calendar_activated = True
                        log_step("通过点击标签成功激活日历选择器", "成功", "符合预期")
            except Exception as e:
                log_step(f"点击入住时间标签失败: {str(e)}", "警告")
        
        # 如果仍然无法激活日历，直接返回失败
        if not calendar_activated:
            log_step("所有尝试都无法激活日历选择器", "失败", "不符合预期")
            return False
        
        # 截图记录日历状态
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}3_calendar_open.png")
        
        # === 日期选择实现 ===
        # 1. 选择入住日期
        check_in_selected = await select_date_in_calendar(page, check_in_date)
        if not check_in_selected:
            log_step("选择入住日期失败", "失败", "不符合预期")
            return False
        
        # 截图记录入住日期选择后的状态
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}3_checkin_selected.png")
        
        # 等待一下确保入住日期被记录
        await page.wait_for_timeout(1000)
        
        # 2. 选择离店日期
        check_out_selected = await select_date_in_calendar(page, check_out_date)
        if not check_out_selected:
            log_step("选择离店日期失败", "失败", "不符合预期")
            return False
        
        # 截图记录离店日期选择后的状态
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}3_checkout_selected.png")
        
        # 等待日历自动关闭
        await page.wait_for_timeout(2000)
        
        # 日历选择完成后验证结果
        # 验证日期是否已正确设置
        date_verification = await verify_date_selection(page, Config.CHECK_IN_DATE, "入住")
        date_verification = await verify_date_selection(page, Config.CHECK_OUT_DATE, "退房") and date_verification
        
        if date_verification:
            log_step("日期设置成功并已验证", "成功", "符合预期")
            return True
        else:
            log_step("日期设置可能不正确", "失败", "不符合预期")
            return False
            
    except Exception as e:
        log_step(f"设置日期时出错: {str(e)}", "失败", "不符合预期")
        return False

async def select_date_in_calendar(page, target_date):
    """
    在日历中选择特定日期
    
    参数:
    - page: Playwright页面对象
    - target_date: 目标日期 (datetime对象)
    
    返回:
    - 成功返回True，失败返回False
    """
    try:
        log_step(f"开始选择 {target_date.strftime('%Y年%m月%d日')}", "信息")
        target_year = target_date.year
        target_month = target_date.month
        target_day = target_date.day
        
        # 先截图保存当前日历状态
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}calendar_before_select_{target_month}_{target_day}.png")
        
        # 日历面板容器选择器 - 根据用户截图定位
        calendar_container = '.c-calendar, .calendar-container, .m-calendar'
        
        # 确保日历已打开
        if not await page.is_visible(calendar_container, timeout=2000):
            log_step("日历选择器未显示，无法选择日期", "失败", "不符合预期")
            return False
        
        # 检测左右两个月份面板 - 使用更精确的选择器
        month_panel_selector = '.c-calendar-month, .month-panel, div[class*="calendar"] > div'
        month_title_selector = 'h3, .title, [class*="title"]'
        
        # 获取当前显示的月份信息
        month_panels = await page.query_selector_all(month_panel_selector)
        if len(month_panels) < 1:
            log_step("无法找到月份面板", "失败", "不符合预期")
            return False
        
        log_step(f"找到 {len(month_panels)} 个月份面板", "信息")
        
        # 获取两个面板的月份标题
        panel_months = []
        for i, panel in enumerate(month_panels):
            try:
                title_elem = await panel.query_selector(month_title_selector)
                if title_elem:
                    title_text = await title_elem.text_content()
                    log_step(f"面板 {i+1} 月份标题: {title_text}", "信息")
                    
                    # 尝试解析年月信息
                    match = re.search(r'(\d{4})年\s*(\d{1,2})月', title_text)
                    if match:
                        year = int(match.group(1))
                        month = int(match.group(2))
                        panel_months.append({
                            'panel_index': i,
                            'year': year,
                            'month': month,
                            'text': title_text
                        })
            except Exception as e:
                log_step(f"解析面板 {i+1} 月份时出错: {str(e)}", "警告")
        
        if not panel_months:
            log_step("无法解析任何月份面板的标题", "失败", "不符合预期")
            return False
        
        # 查找目标月份是否在当前视图中
        target_panel = None
        for panel_info in panel_months:
            if panel_info['year'] == target_year and panel_info['month'] == target_month:
                target_panel = panel_info
                log_step(f"找到目标月份 {target_year}年{target_month}月 在面板 {panel_info['panel_index']+1}", "成功", "符合预期")
                break
        
        # 如果目标月份不在当前视图，需要导航
        if not target_panel:
            log_step(f"目标月份 {target_year}年{target_month}月 不在当前视图，尝试导航", "信息")
            
            # 找到月份导航按钮
            prev_month_btn = '.c-calendar-icon-prev, .prev-btn, .btn-prev, [class*="prev"]'
            next_month_btn = '.c-calendar-icon-next, .next-btn, .btn-next, [class*="next"]'
            
            # 计算与当前显示月份的差距
            ref_panel = panel_months[0]  # 使用第一个面板作为参考
            target_date_value = target_year * 12 + target_month
            ref_date_value = ref_panel['year'] * 12 + ref_panel['month']
            month_diff = target_date_value - ref_date_value
            
            log_step(f"目标月份与参考月份 {ref_panel['text']} 相差 {month_diff} 个月", "信息")
            
            # 根据月份差决定导航方向和次数
            if month_diff < 0:
                # 向前导航
                log_step(f"需要向前导航 {abs(month_diff)} 个月", "信息")
                for i in range(min(abs(month_diff), 12)):  # 限制最多12次避免无限循环
                    # 检查前一月按钮是否可见且未禁用
                    if not await page.is_visible(prev_month_btn, timeout=1000):
                        log_step("向前导航按钮不可见", "失败", "不符合预期")
                        break
                        
                    # 检查是否禁用
                    is_disabled = await page.evaluate(f"""
                        () => {{
                            const btn = document.querySelector('{prev_month_btn}');
                            return btn && (btn.classList.contains('is-disable') || 
                                  btn.classList.contains('disabled') || 
                                  btn.hasAttribute('disabled'));
                        }}
                    """)
                    
                    if is_disabled:
                        log_step("向前导航按钮已禁用", "失败", "不符合预期")
                        break
                    
                    # 点击前一月按钮
                    await page.click(prev_month_btn)
                    await page.wait_for_timeout(800)  # 等待面板更新
                    
                    # 检查是否已达到目标月份
                    updated_panels = await page.query_selector_all(month_panel_selector)
                    for idx, panel in enumerate(updated_panels):
                        try:
                            title_elem = await panel.query_selector(month_title_selector)
                            if title_elem:
                                title_text = await title_elem.text_content()
                                if re.search(f'{target_year}年\\s*{target_month}月', title_text):
                                    target_panel = {'panel_index': idx, 'year': target_year, 'month': target_month}
                                    log_step(f"已导航到目标月份 {target_year}年{target_month}月 在面板 {idx+1}", "成功", "符合预期")
                                    break
                        except Exception as e:
                            log_step(f"导航检查时出错: {str(e)}", "警告")
                    
                    if target_panel:
                        break
            elif month_diff > 0:
                # 向后导航
                log_step(f"需要向后导航 {month_diff} 个月", "信息")
                for i in range(min(month_diff, 12)):  # 限制最多12次避免无限循环
                    # 检查后一月按钮是否可见且未禁用
                    if not await page.is_visible(next_month_btn, timeout=1000):
                        log_step("向后导航按钮不可见", "失败", "不符合预期")
                        break
                        
                    # 检查是否禁用
                    is_disabled = await page.evaluate(f"""
                        () => {{
                            const btn = document.querySelector('{next_month_btn}');
                            return btn && (btn.classList.contains('is-disable') || 
                                  btn.classList.contains('disabled') || 
                                  btn.hasAttribute('disabled'));
                        }}
                    """)
                    
                    if is_disabled:
                        log_step("向后导航按钮已禁用", "失败", "不符合预期")
                        break
                    
                    # 点击后一月按钮
                    await page.click(next_month_btn)
                    await page.wait_for_timeout(800)  # 等待面板更新
                    
                    # 检查是否已达到目标月份
                    updated_panels = await page.query_selector_all(month_panel_selector)
                    for idx, panel in enumerate(updated_panels):
                        try:
                            title_elem = await panel.query_selector(month_title_selector)
                            if title_elem:
                                title_text = await title_elem.text_content()
                                if re.search(f'{target_year}年\\s*{target_month}月', title_text):
                                    target_panel = {'panel_index': idx, 'year': target_year, 'month': target_month}
                                    log_step(f"已导航到目标月份 {target_year}年{target_month}月 在面板 {idx+1}", "成功", "符合预期")
                                    break
                        except Exception as e:
                            log_step(f"导航检查时出错: {str(e)}", "警告")
                    
                    if target_panel:
                        break
        
        # 如果无法找到目标月份，返回失败
        if not target_panel:
            log_step(f"导航后仍无法找到目标月份 {target_year}年{target_month}月", "失败", "不符合预期")
            return False
        
        # 在找到的目标月份面板中选择日期
        panel_idx = target_panel['panel_index']
        log_step(f"在面板 {panel_idx+1} 中查找日期 {target_day}", "信息")
        
        # 截图保存找到目标月份的状态
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}calendar_found_month_{target_month}.png")
        
        # 精确定位目标月份面板
        panel_selector = f".c-calendar-month:nth-child({panel_idx+1})"
        if not await page.is_visible(panel_selector, timeout=1000):
            panel_selector = f".c-calendar-month"
            if panel_idx > 0:
                panel_selector += f":nth-of-type({panel_idx+1})"
        
        date_found = False
        
        try:
            # 使用更直接的JavaScript代码寻找指定日期并点击
            # 这段代码通过直接在DOM中找到当前面板中的所有日期元素，然后根据文本内容匹配目标日
            date_found = await page.evaluate(f"""
                () => {{
                    // 记录所有调试信息
                    const debugInfo = [];
                    
                    // 提供多种可能的日期容器选择器
                    const containerSelectors = [
                        '.c-calendar-month:nth-child({panel_idx+1})',
                        '.c-calendar-month:nth-of-type({panel_idx+1})',
                        '.c-calendar-month',
                        'div[class*="calendar"] > div:nth-child({panel_idx+1})',
                        'div[class*="calendar-month"]',
                        'div[class*="month-panel"]'
                    ];
                    
                    // 提供多种可能的日期单元格选择器
                    const dayCellSelectors = [
                        'li[class*="allow-hover"]', 
                        'li:not([class*="disable"])', 
                        'li[tabindex]',
                        'td[class*="day"]',
                        'div[class*="day"]',
                        'li', // 最通用的选择器
                        'td' 
                    ];
                    
                    // 首先获取所有月份面板
                    const allMonthPanels = document.querySelectorAll('.c-calendar-month, div[class*="calendar"] > div, div[class*="month"]');
                    debugInfo.push(`找到 ${{allMonthPanels.length}} 个可能的月份面板`);
                    
                    // 遍历所有面板，查找是否有日期29
                    let targetText = '{target_month}月';
                    
                    // 找到特定月份的面板
                    let targetMonthPanel = null;
                    for (const panel of allMonthPanels) {{
                        const titleElem = panel.querySelector('h3, div[class*="title"], [class*="month"]');
                        if (titleElem) {{
                            const titleText = titleElem.textContent;
                            debugInfo.push(`面板标题: ${{titleText}}`);
                            
                            // 寻找包含目标月份的面板
                            if (titleText.includes('{target_year}年') && titleText.includes(`{target_month}月`)) {{
                                targetMonthPanel = panel;
                                debugInfo.push(`找到目标月份面板: ${{titleText}}`);
                                break;
                            }}
                        }}
                    }}
                    
                    // 如果没有直接找到月份面板，尝试使用选择器方法
                    if (!targetMonthPanel) {{
                        debugInfo.push('未通过标题找到目标月份面板，尝试选择器方法');
                        
                        let container = null;
                        // 尝试找到日期容器
                        for (const selector of containerSelectors) {{
                            const elements = document.querySelectorAll(selector);
                            if (elements && elements.length > 0) {{
                                // 如果有多个面板，选择panel_idx指定的那个，否则选第一个
                                container = elements.length > {panel_idx} ? elements[{panel_idx}] : elements[0];
                                debugInfo.push(`通过选择器找到日期容器: ${{selector}}`);
                                if (container) break;
                            }}
                        }}
                        targetMonthPanel = container;
                    }}
                    
                    if (!targetMonthPanel) {{
                        debugInfo.push('未能找到任何日期容器面板');
                        console.log(debugInfo.join('\\n'));
                        return false;
                    }}
                    
                    // 输出当前月份面板的HTML结构，辅助调试
                    debugInfo.push(`月份面板HTML: ${{targetMonthPanel.outerHTML.substring(0, 150)}}...`);
                    
                    // 在容器中查找所有日期单元格
                    let targetDay = null;
                    
                    // 先获取面板中所有可能的日期容器(日期表格/列表)
                    const dayContainers = targetMonthPanel.querySelectorAll('ul, table, div[class*="days"]');
                    debugInfo.push(`找到 ${{dayContainers.length}} 个日期容器`);
                    
                    // 如果有日期容器，优先从中寻找
                    if (dayContainers.length > 0) {{
                        for (const container of dayContainers) {{
                            // 获取容器中所有单元格
                            for (const selector of dayCellSelectors) {{
                                const cells = container.querySelectorAll(selector);
                                debugInfo.push(`日期容器中找到 ${{cells.length}} 个可能的日期单元格: ${{selector}}`);
                                
                                // 遍历所有单元格
                                for (const cell of cells) {{
                                    const text = cell.textContent.trim();
                                    // 提取数字
                                    const dayNum = text.replace(/[^0-9]/g, '');
                                    debugInfo.push(`日期单元格: "${{text}}", 提取数字: "${{dayNum}}"`);
                                    
                                    if (dayNum === '{target_day}') {{
                                        // 检查是否禁用
                                        const isDisabled = cell.classList.contains('is-disable') || 
                                                        cell.classList.contains('disabled') || 
                                                        cell.getAttribute('aria-disabled') === 'true' ||
                                                        cell.hasAttribute('disabled');
                                        
                                        if (!isDisabled) {{
                                            targetDay = cell;
                                            debugInfo.push(`找到目标日期 {target_day}: ${{text}}`);
                                            break;
                                        }} else {{
                                            debugInfo.push(`找到目标日期 {target_day} 但已禁用`);
                                        }}
                                    }}
                                }}
                                if (targetDay) break;
                            }}
                            if (targetDay) break;
                        }}
                    }} else {{
                        // 直接从月份面板寻找日期单元格
                        for (const selector of dayCellSelectors) {{
                            const cells = targetMonthPanel.querySelectorAll(selector);
                            debugInfo.push(`未找到日期容器，直接查找到 ${{cells.length}} 个可能的日期单元格: ${{selector}}`);
                            
                            // 输出所有单元格的文本内容，辅助调试
                            if (cells.length > 0 && cells.length < 50) {{
                                const cellTexts = Array.from(cells).map(c => c.textContent.trim()).join(', ');
                                debugInfo.push(`单元格文本内容: ${{cellTexts}}`);
                            }}
                            
                            // 遍历所有单元格，查找匹配目标日的单元格
                            for (const cell of cells) {{
                                const text = cell.textContent.trim();
                                // 提取数字
                                const dayNum = text.replace(/[^0-9]/g, '');
                                
                                if (dayNum === '{target_day}') {{
                                    // 检查是否禁用
                                    const isDisabled = cell.classList.contains('is-disable') || 
                                                    cell.classList.contains('disabled') || 
                                                    cell.getAttribute('aria-disabled') === 'true' ||
                                                    cell.hasAttribute('disabled');
                                    
                                    if (!isDisabled) {{
                                        targetDay = cell;
                                        debugInfo.push(`找到目标日期 {target_day}: ${{text}}`);
                                        break;
                                    }} else {{
                                        debugInfo.push(`找到目标日期 {target_day} 但已禁用`);
                                    }}
                                }}
                            }}
                            if (targetDay) break;
                        }}
                    }}
                    
                    // 如果找到目标日期，点击它
                    if (targetDay) {{
                        debugInfo.push('准备点击目标日期...');
                        console.log(debugInfo.join('\\n'));
                        targetDay.click();
                        return true;
                    }}
                    
                    debugInfo.push('未能找到可点击的目标日期 {target_day}');
                    console.log(debugInfo.join('\\n'));
                    return false;
                }}
            """)
            
            if date_found:
                log_step(f"已通过JavaScript直接查找并点击日期 {target_day}", "成功", "符合预期")
            else:
                log_step(f"JavaScript方法未能找到可点击的日期 {target_day}", "失败", "不符合预期")
        except Exception as e:
            log_step(f"使用JavaScript查找日期时出错: {str(e)}", "警告")
            
        # 截图保存日期选择后的状态
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}calendar_after_click_{target_month}_{target_day}.png")
        
        # 验证日期选择结果
        if not date_found:
            log_step(f"无法在月份 {target_year}年{target_month}月 中找到并点击日期 {target_day}", "失败", "不符合预期")
            return False
        
        # 等待日期选择被处理
        await page.wait_for_timeout(1000)
        return True
    except Exception as e:
        log_step(f"选择日期时出错: {str(e)}", "失败", "不符合预期")
        # 获取更多错误上下文
        error_stack = f"\n错误堆栈: {traceback.format_exc()}"
        log_step(error_stack, "失败")
        return False

# 修改set_search_parameters方法，移除日期处理代码
async def set_search_parameters(page):
    """设置搜索参数（目的地、日期）"""
    log_step("正在设置搜索参数...")
    
    try:
        # 设置目的地 - 使用Playwright的原生方法
        log_step("正在设置目的地...")
        
        # 找到并点击目的地输入框
        destination_selectors = [
            'input[placeholder*="目的地"]',
            'input[placeholder*="城市"]',
            '#hotels-destination',
            '.destination-input',
            '#J_search_attractions'
        ]
        
        destination_input_found = False
        for selector in destination_selectors:
            try:
                if await page.is_visible(selector, timeout=2000):
                    # 点击输入框激活
                    await page.click(selector)
                    await page.wait_for_timeout(500)
                    
                    # 清空输入框
                    await page.fill(selector, '')
                    await page.wait_for_timeout(500)
                    
                    # 输入目的地
                    await page.fill(selector, Config.DESTINATION)
                    log_step(f"已输入目的地: {Config.DESTINATION}", "成功", "符合预期")
                    destination_input_found = True
                    
                    # 等待下拉菜单显示
                    await page.wait_for_timeout(Config.DESTINATION_WAIT)
                    
                    # 尝试截图保存当前状态
                    if Config.DEBUG:
                        await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}2_destination_input.png")
                    
                    # 再次点击输入框以确认选择（根据用户截图显示的操作方式）
                    await page.click(selector)
                    log_step("已点击输入框确认目的地选择", "成功", "符合预期")
                    
                    # 等待选择后页面稳定
                    await page.wait_for_timeout(1000)
                    
                    # 截图记录目的地设置结果
                    if Config.DEBUG:
                        await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}2_destination_set.png")
                    
                    break
            except Exception as e:
                log_step(f"尝试设置目的地 {selector} 时遇到错误: {str(e)}", "警告")
                continue
        
        if not destination_input_found:
            log_step("未找到目的地输入框", "失败", "不符合预期")
            return False
        
        # 设置酒店名称 - 使用Playwright的原生方法
        log_step("正在设置酒店名称...")
        keyword_selectors = [
            '#keyword',
            'input[placeholder*="酒店名称"]',
            'input.search-input',
            'input[placeholder*="关键词"]'
        ]
        
        hotel_name_set = False
        for keyword_selector in keyword_selectors:
            try:
                if await page.is_visible(keyword_selector, timeout=2000):
                    # 点击输入框激活
                    await page.click(keyword_selector, timeout=5000)
                    await page.wait_for_timeout(500)
                    
                    # 清空输入框
                    await page.fill(keyword_selector, '')
                    await page.wait_for_timeout(500)
                    
                    # 输入酒店名称
                    await page.fill(keyword_selector, Config.HOTEL_NAME)
                    log_step(f"已设置酒店名称: {Config.HOTEL_NAME}", "成功", "符合预期")
                    hotel_name_set = True
                    
                    # 等待输入完成
                    await page.wait_for_timeout(1000)
                    break
            except Exception as e:
                log_step(f"尝试设置酒店名称 {keyword_selector} 时出错: {str(e)}", "警告")
                continue
        
        if not hotel_name_set:
            log_step("无法设置酒店名称，但可以继续", "警告")
        
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}2_hotel_name_set.png")
        
        # 调用新方法设置日期
        date_set_success = await set_date_parameters(page)
        if not date_set_success:
            log_step("设置日期失败，但尝试继续执行", "警告")
        
        # 验证目的地设置是否成功
        verify_destination_script = """
        (expectedDestination) => {
            // 找到目的地输入框
            const destinationInput = document.querySelector('input[placeholder*="目的地"]') || 
                              document.querySelector('input[placeholder*="城市"]') || 
                              document.querySelector('#hotels-destination') ||
                              document.querySelector('.destination-input');
                              
            if (destinationInput) {
                return {
                    found: true,
                    value: destinationInput.value,
                    matches: destinationInput.value.toLowerCase().includes('高松') || 
                             destinationInput.value.toLowerCase().includes('takamatsu')
                };
            } else {
                return {
                    found: false
                };
            }
        }
        """
        
        destination_check = await page.evaluate(verify_destination_script, Config.DESTINATION)
        if destination_check.get('found') and destination_check.get('matches'):
            log_step(f"目的地设置验证成功: {destination_check.get('value')}", "成功", "符合预期")
            return True
        elif destination_check.get('found'):
            log_step(f"目的地设置可能不正确: {destination_check.get('value')}", "警告")
            return True
        else:
            log_step("无法验证目的地设置", "失败", "不符合预期")
            return False
    except Exception as e:
        log_step(f"设置搜索参数时出错: {str(e)}", "失败", "不符合预期")
        return False

# 搜索酒店函数，使用JavaScript直接触发
async def search_hotel(page):
    """执行酒店搜索"""
    log_step("正在执行酒店搜索...")
    
    try:
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}3_before_search.png")
        
        # 直接尝试点击搜索按钮
        search_btn_selectors = [
            'button.search-btn-wrap', 
            'button[aria-label*="搜索"]',
            'button[aria-label="按钮：查询酒店"]',
            'button.primary-btn', 
            'button.search-btn', 
            'button[type="submit"]',
            '.search-btn',
            'button:has-text("搜索")',
            'button:has-text("查询")'
        ]
        
        search_btn_clicked = False
        for selector in search_btn_selectors:
            try:
                if await page.is_visible(selector, timeout=2000):
                    # 记录搜索按钮文本
                    btn_text = await page.text_content(selector)
                    log_step(f"找到搜索按钮: {btn_text}", "成功", "符合预期")
                    
                    # 点击搜索按钮
                    await page.click(selector)
                    log_step("已点击搜索按钮", "成功", "符合预期")
                    search_btn_clicked = True
                    break
            except Exception as e:
                log_step(f"尝试点击搜索按钮 {selector} 时出错: {str(e)}", "警告")
                continue
        
        if not search_btn_clicked:
            # 如果未能点击搜索按钮，尝试使用JavaScript直接触发
            log_step("未找到搜索按钮，尝试使用JavaScript触发搜索...", "警告")
            
            submit_form_script = """
            () => {
                const searchBtn = document.querySelector('button.search-btn-wrap') || 
                               document.querySelector('button[aria-label*="搜索"]') ||
                               document.querySelector('button[aria-label="按钮：查询酒店"]') ||
                               document.querySelector('button.primary-btn') || 
                               document.querySelector('button.search-btn') || 
                               document.querySelector('button[type="submit"]') ||
                               document.querySelector('.search-btn');
                
                let result = {
                    success: false,
                    method: 'none'
                };
                
                // 如果找到了搜索按钮
                if (searchBtn) {
                    try {
                        // 记录按钮信息
                        result.button = {
                            text: searchBtn.textContent.trim()
                        };
                        
                        // 模拟DOM事件
                        const clickEvent = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        });
                        
                        // 直接分发事件
                        searchBtn.dispatchEvent(clickEvent);
                        
                        result.success = true;
                        result.method = 'buttonClick';
                    } catch (e) {
                        result.error = e.toString();
                    }
                } else {
                    // 如果没有找到搜索按钮，尝试提交表单
                    const forms = document.querySelectorAll('form');
                    if (forms.length > 0) {
                        try {
                            forms[0].submit();
                            result.success = true;
                            result.method = 'formSubmit';
                        } catch (e) {
                            result.formError = e.toString();
                        }
                    }
                }
                
                return result;
            }
            """
            
            # 执行表单提交
            submit_result = await page.evaluate(submit_form_script)
            if submit_result.get('success'):
                log_step(f"使用JavaScript触发搜索成功，方法: {submit_result.get('method')}", "成功", "符合预期")
            else:
                log_step("无法使用任何方法触发搜索", "失败", "不符合预期")
                return False
        
        # 等待页面加载
        try:
            await page.wait_for_load_state("networkidle", timeout=Config.TIMEOUT)
            log_step("搜索结果页面已加载", "成功", "符合预期")
            
            # 验证搜索结果页面状态
            if Config.DEBUG:
                await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}4_search_results.png")
            
            # 验证URL变化
            current_url = page.url
            log_step(f"搜索后URL: {current_url}", "信息")
            
            # 根据URL和页面标题判断是否成功搜索
            page_title = await page.title()
            log_step(f"搜索后页面标题: {page_title}", "信息")
            
            # 如果URL或标题包含搜索相关关键词，认为搜索成功
            if ("list" in current_url.lower() or 
                "search" in current_url.lower() or 
                "搜索" in page_title or 
                "查询" in page_title or
                "酒店列表" in page_title):
                log_step("搜索成功跳转到结果页面", "成功", "符合预期")
                return True
            else:
                log_step("页面已加载，但可能不是搜索结果页面", "失败", "不符合预期")
                return False
        except Exception as e:
            log_step(f"等待搜索结果页面加载超时: {str(e)}", "失败", "不符合预期")
            return False
    except Exception as e:
        log_step(f"执行搜索时出错: {str(e)}", "失败", "不符合预期")
        return False

# 在搜索结果中查找匹配的酒店
async def find_target_hotel(page):
    """在搜索结果中查找目标酒店"""
    log_step(f"正在搜索结果中查找目标酒店: {Config.HOTEL_NAME}...")
    
    # 先尝试查找下拉菜单中是否有完全匹配的结果
    try_dropdown_script = """
    (hotelName) => {
        const result = { found: false, text: '', clicked: false };
        // 查找包含酒店名称的下拉选项
        const dropdowns = document.querySelectorAll('.drop-result-list div, .fav-hotel, .search-result-list, .recent-search-list, .hot-searches > div');
        const hotelLower = hotelName.toLowerCase();
                
        for (const item of dropdowns) {
            const text = item.textContent.toLowerCase();
            if (text.includes(hotelLower) || (text.includes('fav') && text.includes('takamatsu'))) {
                result.found = true;
                result.text = item.textContent.trim();
                
                try {
                    item.click();
                    result.clicked = true;
                } catch (e) {
                    result.error = e.toString();
                }
                break;
            }
        }
        return result;
    }
    """
    
    # 在酒店列表中查找的脚本
    find_hotel_script = """
    (hotelName) => {
        const hotelNameLower = hotelName.toLowerCase();
        const results = {
            found: false,
            url: null,
            name: null,
            hotelItems: 0
        };
        
        // 搜索结果列表的所有可能选择器
        const selectors = [
            '.hotel-list .hotel-item',
            '.J_HotelList .hotel-item-link',
            '.hotel-list-item',
            '.e_hotel_list .e_hotel_item',
            '.hotel-info', // 更通用的选择器
            '[data-hotel]', // 可能存在的数据属性
            '.J_HotelItem',
            '.item_hotel'
        ];
        
        // 尝试每一个选择器
        for (const selector of selectors) {
            const items = document.querySelectorAll(selector);
            results.hotelItems += items.length;
            
            for (const item of items) {
                // 查找酒店名称元素
                const nameElem = item.querySelector('.hotel-name, .name, h2, .title, .htl-name') || item;
                const name = nameElem.textContent.trim().toLowerCase();
                
                if (name.includes(hotelNameLower) || (name.includes('fav') && name.includes('takamatsu'))) {
                    results.found = true;
                    results.name = name;
                    
                    // 查找链接
                    const link = item.tagName === 'A' ? item : item.querySelector('a');
                    if (link) {
                        results.url = link.href;
                    }
                    return results;
                }
            }
        }
        
        // 检查页面上是否有直接显示的酒店结果
        const singleHotelTitle = document.querySelector('.hotel-title, .detail-headline, .hotel-name');
        if (singleHotelTitle && (singleHotelTitle.textContent.trim().toLowerCase().includes(hotelNameLower) || 
            (singleHotelTitle.textContent.toLowerCase().includes('fav') && singleHotelTitle.textContent.toLowerCase().includes('takamatsu')))) {
            results.found = true;
            results.name = singleHotelTitle.textContent.trim();
            results.url = window.location.href;
        }
        
        return results;
    }
    """
    
    try:
        # 先截个图，看看搜索结果的状态
        if Config.DEBUG:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}5_before_find_hotel.png")
            
        # 先检查是否有下拉选项可以直接点击
        dropdown_result = await page.evaluate(try_dropdown_script, Config.HOTEL_NAME)
        if dropdown_result.get('found'):
            log_step(f"在下拉选项中找到匹配: {dropdown_result.get('text')}", "成功", "符合预期")
            if dropdown_result.get('clicked'):
                log_step("已点击下拉选项", "成功", "符合预期")
                await page.wait_for_load_state("networkidle")
                
                if Config.DEBUG:
                    await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}5_1_dropdown_clicked.png")
                    
                # 验证是否已进入酒店详情页
                hotel_found = await verify_hotel_found(page, Config.HOTEL_NAME)
                if hotel_found:
                    log_step("通过点击下拉选项找到酒店", "成功", "符合预期")
                    return True
                else:
                    log_step("点击下拉选项后未直接进入酒店详情页", "信息")
        
        # 尝试在搜索结果中查找酒店
        results = await page.evaluate(find_hotel_script, Config.HOTEL_NAME)
        
        if results['found']:
            log_step(f"在搜索结果中找到目标酒店: {results['name']}", "成功", "符合预期")
            if results['url']:
                log_step(f"酒店URL: {results['url']}", "成功", "符合预期")
                # 如果找到了URL，可以直接访问
                try:
                    await page.goto(results['url'], timeout=Config.TIMEOUT)
                    await page.wait_for_load_state("networkidle")
                    log_step("已跳转到酒店详情页", "成功", "符合预期")
                    
                    if Config.DEBUG:
                        await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}6_hotel_details.png")
                        
                    return True
                except Exception as e:
                    log_step(f"跳转到酒店详情页失败: {str(e)}", "失败", "不符合预期")
            else:
                log_step("找到酒店但未获取到URL", "失败", "不符合预期")
        else:
            log_step(f"在搜索结果中未找到目标酒店，找到了 {results['hotelItems']} 个其他酒店", "失败", "不符合预期")
            
            # 如果没找到，尝试搜索下拉建议选择
            suggestion_script = """
            (hotelName) => {
                const hotelNameLower = hotelName.toLowerCase();
                const results = { found: false, clicked: false };
                
                // 检查是否有下拉建议
                const suggestions = document.querySelectorAll('.drop-result-list div, .search-suggest-list li, .result-list div');
                for (const suggestion of suggestions) {
                    const text = suggestion.textContent.toLowerCase();
                    if (text.includes(hotelNameLower) || (text.includes('fav') && text.includes('takamatsu'))) {
                        results.found = true;
                        results.text = suggestion.textContent.trim();
                        try {
                            suggestion.click();
                            results.clicked = true;
                        } catch (e) {
                            results.error = e.toString();
                        }
                        break;
                    }
                }
                return results;
            }
            """
            
            try:
                suggestion_results = await page.evaluate(suggestion_script, Config.HOTEL_NAME)
                if suggestion_results['found']:
                    log_step(f"找到匹配的搜索建议: {suggestion_results['text']}", "成功", "符合预期")
                    if suggestion_results['clicked']:
                        log_step("已点击搜索建议", "成功", "符合预期")
                        # 等待页面跳转和加载
                        await page.wait_for_load_state("networkidle")
                        
                        if Config.DEBUG:
                            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}6_after_suggestion.png")
                            
                        return await find_target_hotel(page)  # 递归调用检查结果
                    else:
                        log_step(f"点击搜索建议失败: {suggestion_results.get('error', '未知错误')}", "失败", "不符合预期")
                else:
                    log_step("未找到匹配的搜索建议", "失败", "不符合预期")
            except Exception as e:
                log_step(f"处理搜索建议时出错: {str(e)}", "失败", "不符合预期")
        
        return False
    except Exception as e:
        log_step(f"查找目标酒店时出错: {str(e)}", "失败", "不符合预期")
        return False

# 使用JavaScript提取房型信息
room_info_script = """
() => {
    const roomInfo = [];
    
    // 尝试多种房型列表选择器
    const roomSelectors = [
        '.room-list .room-card',
        '.base-room-list .room-item',
        '.J_RoomList .r-item',
        '.hotelRoomList .room-item',
        '.hotel-detail-room-list .room-box',
        '.room-list'
    ];
    
    // 对每种选择器尝试查找房型
    for (const selector of roomSelectors) {
        const rooms = document.querySelectorAll(selector);
        if (rooms && rooms.length > 0) {
            // 遍历房型列表
            rooms.forEach((room, index) => {
                // 提取房型名称
                const nameElem = room.querySelector('.room-name, .name, .title, h2, .room-title');
                const name = nameElem ? nameElem.textContent.trim() : `未知房型${index + 1}`;
                
                // 提取房型价格
                const priceElem = room.querySelector('.room-price, .price, .cost, .room-rate, .room-total, .unit-price, .total-price .num, [data-role="price"]');
                const price = priceElem ? priceElem.textContent.trim() : '价格未知';
                
                // 提取房型设施信息
                const facilitiesElem = room.querySelector('.facilities, .room-facilities, .service-list, .room-info');
                const facilities = facilitiesElem ? facilitiesElem.textContent.trim() : '设施信息未知';
                
                // 提取其他可能有用的信息
                const breakfast = room.textContent.includes('含早') ? '含早餐' : '不含早餐';
                const cancelInfo = room.querySelector('.cancel-policy, .policy') ? 
                    room.querySelector('.cancel-policy, .policy').textContent.trim() : '取消政策未知';
                
                roomInfo.push({
                    name,
                    price,
                    breakfast,
                    cancelInfo,
                    facilities
                });
            });
            
            // 如果找到了房型，就不再继续查找
            if (roomInfo.length > 0) {
                break;
            }
        }
    }
    
    // 如果通过常规选择器没找到房型，尝试查找任何可能包含房型信息的元素
    if (roomInfo.length === 0) {
        // 查找包含"房型"、"客房"或"房间"字样的区域
        const possibleRoomSections = Array.from(document.querySelectorAll('div, section'))
            .filter(el => el.textContent.includes('房型') || el.textContent.includes('客房') || el.textContent.includes('房间'));
        
        if (possibleRoomSections.length > 0) {
            // 使用第一个可能的区域
            const section = possibleRoomSections[0];
            
            // 尝试识别价格模式
            let price = '价格未知';
            const pricePattern = /¥\\s*\\d+(\\.\\d+)?|\\d+(\\.\\d+)?\\s*元/;
            const priceMatch = section.textContent.match(pricePattern);
            if (priceMatch) {
                price = priceMatch[0];
            }
            
            roomInfo.push({
                name: '可能的房型信息',
                price: price,
                info: section.textContent.replace(/\\s+/g, ' ').substring(0, 500) + '...'
            });
        }
    }
    
    return {
        count: roomInfo.length,
        rooms: roomInfo,
        pageTitle: document.title,
        currentUrl: window.location.href
    };
}
"""

# ==================== 第二部分：酒店列表页处理 ====================

async def extract_hotel_list_info(page):
    """提取酒店列表页中的酒店信息"""
    log_step("开始提取酒店列表页信息")
    
    # 仅在需要保存临时文件时保存截图
    if Config.SAVE_TEMP_FILES:
        await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}hotel_list_page.png")
    
    # 固定等待10秒，确保页面完全加载
    log_step("等待10秒，确保页面完全加载")
    await page.wait_for_timeout(10000)
    
    # 等待酒店列表加载 - 使用更精确的选择器
    try:
        # 首先等待list-item-target元素出现
        await page.wait_for_selector('li.list-item-target, li[class*="list-item-target"]', timeout=Config.TIMEOUT)
        log_step("酒店列表项已加载", "成功")
    except Exception as e:
        log_step(f"等待酒店列表加载失败: {str(e)}", "失败")
        # 仅在需要保存临时文件时保存页面源码
        if Config.SAVE_TEMP_FILES:
            content = await page.content()
            with open("hotel_list_page.html", "w", encoding="utf-8") as f:
                f.write(content)
            log_step("已保存列表页源码到hotel_list_page.html", "信息")
        return [], None
    
    # 查找所有酒店列表项
    list_items = await page.query_selector_all('li.list-item-target, li[class*="list-item-target"]')
    
    if not list_items or len(list_items) == 0:
        log_step("未找到酒店列表项", "失败")
        return [], None
    
    log_step(f"找到 {len(list_items)} 个酒店列表项", "成功")
    
    # 选择第一个列表项作为目标酒店（根据要求）
    target_item = list_items[0]
    log_step("选择第一个列表项作为目标酒店", "成功")
    
    # 在目标列表项内查找酒店卡片
    hotel_card = await target_item.query_selector('div.hotel-card, div[class*="hotel-card"]')
    
    if not hotel_card:
        log_step("在目标列表项中未找到酒店卡片", "失败")
        return [], None
    
    # 提取酒店信息
    try:
        # 1. 提取酒店名称
        name_el = await hotel_card.query_selector('.name-text, [class*="name"], h2, .title')
        hotel_name = await name_el.text_content() if name_el else "未知酒店"
        
        # 2. 提取酒店价格
        price_el = await hotel_card.query_selector('.price .ave-price-num, [class*="price"], .room-price')
        price = await price_el.text_content() if price_el else "价格未知"
        
        # 3. 提取酒店评分
        score_el = await hotel_card.query_selector('.score-info .score-value, [class*="score"], .rating')
        score = await score_el.text_content() if score_el else "评分未知"
        
        # 4. 提取hotelName和subtitle
        hotel_name_el = await hotel_card.query_selector('span.hotelName, [class*="hotelName"]')
        subtitle_el = await hotel_card.query_selector('div.hotel-subtitle, [class*="hotel-subtitle"]')
        
        if hotel_name_el:
            hotel_name_text = await hotel_name_el.text_content()
            log_step(f"酒店名称(hotelName): {hotel_name_text}", "信息")
        
        if subtitle_el:
            subtitle_text = await subtitle_el.text_content()
            log_step(f"酒店副标题(subtitle): {subtitle_text}", "信息")
        
        # 5. 提取hotel-head信息
        head_el = await hotel_card.query_selector('div.hotel-head, div[class*="hotel-head"]')
        hotel_head_info = await head_el.evaluate('el => el.outerHTML') if head_el else ""
        
        # 6. 提取room-info信息
        room_info_el = await hotel_card.query_selector('div.room-info, div[class*="room-info"]')
        room_info = await room_info_el.evaluate('el => el.outerHTML') if room_info_el else ""
        
        # 构建酒店信息对象
        hotel_info = {
            "名称": hotel_name.strip(),
            "价格": price.strip(),
            "评分": score.strip(),
            "is_target": True  # 标记为目标酒店
        }
        
        # 如果提取到hotelName和subtitle，添加到信息对象中
        if hotel_name_el:
            hotel_info["hotelName"] = hotel_name_text.strip()
        
        if subtitle_el:
            hotel_info["subtitle"] = subtitle_text.strip()
        
        # 仅在需要保存临时文件时保存HTML内容
        if Config.SAVE_TEMP_FILES:
            # 保存酒店head和room信息到文件
            if hotel_head_info:
                with open("hotel_head_info.html", "w", encoding="utf-8") as f:
                    f.write(hotel_head_info)
                log_step("已保存酒店head信息到hotel_head_info.html", "成功")
            
            if room_info:
                with open("hotel_room_info.html", "w", encoding="utf-8") as f:
                    f.write(room_info)
                log_step("已保存酒店room信息到hotel_room_info.html", "成功")
        
        log_step(f"成功提取目标酒店信息: {hotel_info}", "成功")
        return [hotel_info], hotel_card
        
    except Exception as e:
        log_step(f"提取酒店信息时出错: {str(e)}", "失败")
        traceback.print_exc()
        return [], None

async def enter_hotel_detail(page, target_hotel_card):
    """点击酒店卡片中的查看详情按钮进入详情页"""
    if not target_hotel_card:
        log_step("未指定目标酒店卡片，无法进入详情页", "失败")
        return None
    
    log_step("准备点击进入酒店详情页")
    
    # 精确查找"查看详情"按钮
    try:
        # 1. 尝试查找book-btn容器
        book_wrap = await target_hotel_card.query_selector('div.book-wrap, div[class*="book-wrap"]')
        if not book_wrap:
            log_step("未找到book-wrap容器", "警告")
            book_wrap = target_hotel_card  # 如果没找到，就在整个卡片中查找
        
        # 2. 在容器中查找查看详情按钮
        view_button = await book_wrap.query_selector('span.btn-txt, span[class*="btn-txt"], .book-btn')
        
        if view_button:
            btn_text = await view_button.text_content()
            log_step(f"找到按钮文本: {btn_text}", "成功")
            if "查看详情" in btn_text or "详情" in btn_text:
                log_step("确认找到查看详情按钮", "成功")
            else:
                log_step(f"按钮文本不是查看详情: {btn_text}", "警告")
        else:
            log_step("未找到明确的查看详情按钮，将尝试其他按钮", "警告")
            view_button = await book_wrap.query_selector('button, a[class*="btn"]')
        
        if not view_button:
            log_step("未找到任何可点击的按钮", "失败")
            # 尝试点击整个卡片
            view_button = target_hotel_card
    except Exception as e:
        log_step(f"查找查看详情按钮时出错: {str(e)}", "警告")
        view_button = target_hotel_card  # 出错时尝试点击整个卡片
    
    # 仅在需要保存临时文件时保存截图
    if Config.SAVE_TEMP_FILES:
        await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}before_click_detail.png")
    
    # 确保按钮可见和可点击
    try:
        if view_button:
            await view_button.scroll_into_view_if_needed()
            log_step("已将按钮滚动到可见区域", "成功")
    except Exception:
        log_step("无法滚动到按钮位置，继续尝试点击", "警告")
    
    # 使用expect_page等待新页面打开
    try:
        async with page.context.expect_page(timeout=20000) as new_page_info:
            if view_button:
                # 在点击之前再次确认按钮状态
                is_visible = await view_button.is_visible()
                log_step(f"按钮可见状态: {is_visible}", "信息")
                
                # 执行点击
                await view_button.click()
                log_step(f"已点击{'查看详情按钮' if view_button != target_hotel_card else '酒店卡片'}", "成功")
            else:
                log_step("未找到可点击元素，尝试点击整个酒店卡片", "警告")
                await target_hotel_card.click()
        
        # 获取新打开的页面
        detail_page = await new_page_info.value
        log_step("成功检测到新打开的详情页面", "成功")
        
        # 等待详情页加载
        await detail_page.wait_for_load_state('networkidle', timeout=Config.TIMEOUT)
        log_step("酒店详情页加载完成", "成功")
        
        # 仅在需要保存临时文件时保存截图
        if Config.SAVE_TEMP_FILES:
            await detail_page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}hotel_detail_page.png")
        
        return detail_page
    except Exception as e:
        log_step(f"等待新页面打开失败: {str(e)}", "警告")
        
        # 仅在需要保存临时文件时保存截图
        if Config.SAVE_TEMP_FILES:
            await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}after_click_detail.png")
        
        # 备选方案1: 尝试从现有页面列表中获取新页面
        await asyncio.sleep(5)  # 多等待几秒
        pages = page.context.pages
        if len(pages) > 1:
            log_step("从现有页面列表中找到新页面", "成功")
            detail_page = pages[-1]  # 假设最后一个是新打开的
            try:
                await detail_page.wait_for_load_state('networkidle', timeout=Config.TIMEOUT)
                if Config.SAVE_TEMP_FILES:
                    await detail_page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}hotel_detail_page_alt.png")
                return detail_page
            except Exception as page_err:
                log_step(f"新页面加载失败: {str(page_err)}", "警告")
        
        # 备选方案2: 检查当前页面是否已变为详情页
        try:
            await page.wait_for_selector('.detail-headline, div.mainRoomList__UlISo, div.commonRoomCard__BpNjl', timeout=10000)
            log_step("当前页面已变为酒店详情页", "成功")
            if Config.SAVE_TEMP_FILES:
                await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}hotel_detail_current_page.png")
            return page
        except Exception:
            log_step("当前页面未变为详情页", "失败")
        
        # 所有尝试失败
        log_step("无法进入酒店详情页，尝试最后的备选方案", "警告")
        
        # 备选方案3: 使用已知URL直接打开酒店详情页
        for url in Config.KNOWN_HOTEL_URLS:
            try:
                log_step(f"尝试直接访问已知URL: {url}", "信息")
                # 在当前页打开
                await page.goto(url, timeout=Config.TIMEOUT)
                # 检查是否成功加载了酒店详情页
                try:
                    await page.wait_for_selector('div.mainRoomList__UlISo, div.commonRoomCard__BpNjl', timeout=15000)
                    log_step(f"成功通过URL直接访问酒店详情页", "成功")
                    if Config.SAVE_TEMP_FILES:
                        await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}direct_url_detail_page.png")
                    return page
                except Exception:
                    log_step(f"通过URL访问未能加载房间列表", "警告")
                    continue
            except Exception as url_err:
                log_step(f"访问URL {url} 失败: {str(url_err)}", "警告")
        
        log_step("所有方案都失败，无法进入酒店详情页", "失败")
        return None

# ==================== 第三部分：酒店房间信息提取 ====================

async def extract_room_info(detail_page):
    """从酒店详情页提取房间信息"""
    if not detail_page:
        log_step("无效的详情页，无法提取房间信息", "失败")
        return []
    
    log_step("开始提取酒店房间信息")
    
    # 提取酒店名称
    hotel_name = ""
    try:
        # 尝试各种可能的选择器
        hotel_name_selectors = [
            'h1.detail-headline', 
            '.hotel-name', 
            '.hotel-title',
            'div.hotel-title-box h1',
            'span.hotelName',
            '.detail-top .name'
        ]
        
        for selector in hotel_name_selectors:
            name_el = await detail_page.query_selector(selector)
            if name_el:
                hotel_name = await name_el.text_content()
                hotel_name = hotel_name.strip()
                log_step(f"提取到酒店名称: {hotel_name}", "成功")
                break
        
        if not hotel_name:
            # 如果没找到，尝试使用页面标题
            title = await detail_page.title()
            hotel_name = title.split('-')[0].strip() if '-' in title else title
            log_step(f"使用页面标题作为酒店名称: {hotel_name}", "信息")
    except Exception as e:
        log_step(f"提取酒店名称时出错: {str(e)}", "警告")
        hotel_name = "未知酒店"
    
    # 等待房间列表加载
    try:
        await detail_page.wait_for_selector('div.mainRoomList__UlISo, div.commonRoomCard__BpNjl', timeout=30000)
        log_step("房间列表已加载", "成功")
    except Exception as e:
        log_step(f"等待房间列表加载超时: {str(e)}", "失败")
        # 仅在需要保存临时文件时保存页面源码
        if Config.SAVE_TEMP_FILES:
            content = await detail_page.content()
            with open("hotel_detail_page.html", "w", encoding="utf-8") as f:
                f.write(content)
            log_step("已保存详情页源码到hotel_detail_page.html", "信息")
        return []
    
    # 提取房间类型
    room_types = await detail_page.query_selector_all('div.commonRoomCard__BpNjl')
    log_step(f"找到 {len(room_types)} 种房型", "成功")
    
    rooms_info = []
    
    for i, room_type in enumerate(room_types):
        try:
            # 提取房型名称
            name_el = await room_type.query_selector('.commonRoomCard-title__iYBn2')
            room_name = await name_el.text_content() if name_el else "未知房型"
            log_step(f"提取房型 #{i+1}: {room_name}", "成功")
            
            # 提取床型信息
            bed_el = await room_type.query_selector('.baseRoom-bedsInfo_title__sxCX9')
            bed_info = await bed_el.text_content() if bed_el else "床型信息未知"
            
            # 提取面积和楼层
            area_els = await room_type.query_selector_all('.baseRoom-facility_title__BCMx6')
            area_info = ""
            for area_el in area_els:
                text = await area_el.text_content()
                if "平方米" in text:
                    area_info = text.strip()
                    break
            
            # 提取房间报价列表
            price_items = await room_type.query_selector_all('.saleRoomItemBox__orNIv')
            
            room_offers = []
            for j, price_item in enumerate(price_items):
                try:
                    # 使用更直接的方式提取信息
                    offer_info = {}
                    
                    # 1. 提取早餐信息
                    try:
                        breakfast_els = await price_item.query_selector_all('div:has(i.u-icon_ic_new_nonbreakfast), div:has(i.u-icon_ic_new_breakfast)')
                        breakfast_texts = []
                        for el in breakfast_els:
                            text = await el.text_content()
                            if text and ("早餐" in text or "无早" in text):
                                breakfast_texts.append(text.strip())
                        
                        if breakfast_texts:
                            offer_info["早餐"] = " | ".join(breakfast_texts)
                        else:
                            # 尝试其他方式查找
                            no_breakfast = await price_item.query_selector('div:has-text("无早餐")')
                            if no_breakfast:
                                offer_info["早餐"] = "无早餐"
                            else:
                                with_breakfast = await price_item.query_selector('div:has-text("早餐")')
                                if with_breakfast:
                                    offer_info["早餐"] = await with_breakfast.text_content()
                                else:
                                    offer_info["早餐"] = "早餐信息未知"
                    except Exception as breakfast_err:
                        log_step(f"提取早餐信息时出错: {str(breakfast_err)}", "警告")
                        offer_info["早餐"] = "早餐信息提取失败"
                    
                    # 2. 提取取消政策
                    try:
                        cancel_els = await price_item.query_selector_all('div:has(i.u-icon_ic_new_freecancellation)')
                        cancel_texts = []
                        for el in cancel_els:
                            text = await el.text_content()
                            if text and ("取消" in text):
                                cancel_texts.append(text.strip())
                        
                        if cancel_texts:
                            offer_info["取消政策"] = " | ".join(cancel_texts)
                        else:
                            # 尝试其他方式查找
                            cancel_policy = await price_item.query_selector('div:has-text("取消")')
                            if cancel_policy:
                                offer_info["取消政策"] = await cancel_policy.text_content()
                            else:
                                offer_info["取消政策"] = "取消政策未知"
                    except Exception as cancel_err:
                        log_step(f"提取取消政策时出错: {str(cancel_err)}", "警告")
                        offer_info["取消政策"] = "取消政策提取失败"
                    
                    # 3. 入住人数
                    try:
                        guests_el = await price_item.query_selector('.saleRoomItemBox-guestInfo-adultBox_adultDesc__AfwYg')
                        if guests_el:
                            guests = await guests_el.text_content()
                        else:
                            # 检查是否有多个人图标而没有文本
                            adult_icons = await price_item.query_selector_all('.saleRoomItemBox-guestInfo-adultBox_adultIcon__K9f3Y')
                            if len(adult_icons) > 0:
                                guests = f"x{len(adult_icons)}"
                            else:
                                guests = "x1"  # 默认为1人
                        
                        offer_info["可住人数"] = guests.strip().replace('x', '')
                    except Exception as guests_err:
                        log_step(f"提取入住人数时出错: {str(guests_err)}", "警告")
                        offer_info["可住人数"] = "1"
                    
                    # 4. 价格信息
                    # 4.1 折扣前价格
                    try:
                        original_price_el = await price_item.query_selector('.saleRoomItemBox-priceBox-deletePrice__fuW7u')
                        if original_price_el:
                            original_price = await original_price_el.text_content()
                            offer_info["原价"] = original_price.strip()
                    except Exception as price_err:
                        log_step(f"提取原价时出错: {str(price_err)}", "警告")
                    
                    # 4.2 当前价格 - 尝试多种方式获取
                    try:
                        # 先尝试找特定的价格元素
                        price_selectors = [
                            '.saleRoomItemBox-priceBox-displayPrice__gWiOr',
                            '.saleRoomItemBox-priceBoxForC__NrqJC span:not(.saleRoomItemBox-priceBox-displayPricePrefix__Xka15)',
                            'div[class*="priceBox"] span:not([class*="Prefix"])',
                            '.saleRoomItemBox-priceBox-displayPrice__gWiOr span:last-child',
                            'div[class*="price"] span:has-text("¥")'
                        ]
                        
                        price_found = False
                        for selector in price_selectors:
                            price_el = await price_item.query_selector(selector)
                            if price_el:
                                price_text = await price_el.text_content()
                                # 清理价格文本，去除"均"等前缀
                                price = price_text.replace('均', '').strip()
                                offer_info["价格"] = price
                                price_found = True
                                log_step(f"找到价格: {price}", "成功")
                                break
                        
                        if not price_found:
                            # 尝试使用JavaScript直接获取所有价格元素内容
                            price_texts = await price_item.evaluate('''() => {
                                const priceElements = Array.from(document.querySelectorAll('[class*="price"], [class*="Price"]'));
                                return priceElements
                                    .map(el => el.textContent)
                                    .filter(text => text.includes('¥') || text.includes('￥'))
                                    .map(text => text.trim());
                            }''')
                            
                            if price_texts and len(price_texts) > 0:
                                offer_info["价格"] = price_texts[0].replace('均', '').strip()
                                log_step(f"通过JavaScript找到价格: {offer_info['价格']}", "成功")
                            else:
                                offer_info["价格"] = "价格未知"
                                log_step("未找到价格信息", "警告")
                    except Exception as price_err:
                        log_step(f"提取价格时出错: {str(price_err)}", "警告")
                        offer_info["价格"] = "价格提取失败"
                    
                    # 4.3 促销信息
                    try:
                        promo_el = await price_item.query_selector('.saleRoomItemBox-promotion-discountTag__nE7d9, [class*="discount"], [class*="promotion"]')
                        if promo_el:
                            promotion = await promo_el.text_content()
                            if promotion:
                                offer_info["促销"] = promotion.strip()
                    except Exception as promo_err:
                        log_step(f"提取促销信息时出错: {str(promo_err)}", "警告")
                    
                    room_offers.append(offer_info)
                    log_step(f"成功提取房型 {room_name} 的价格选项 #{j+1}: {offer_info}", "成功")
                    
                except Exception as e:
                    log_step(f"提取房型 {room_name} 的价格选项 #{j+1} 时出错: {str(e)}", "警告")
                    traceback.print_exc()
            
            room_info = {
                "房型名称": room_name.strip(),
                "床型": bed_info.strip(),
                "面积和楼层": area_info,
                "价格选项": room_offers
            }
            
            rooms_info.append(room_info)
            
        except Exception as e:
            log_step(f"提取房型 #{i+1} 信息时出错: {str(e)}", "警告")
            traceback.print_exc()
    
    log_step(f"共提取了 {len(rooms_info)} 种房型的信息", "成功")
    return {"酒店名称": hotel_name, "房型列表": rooms_info}

async def save_room_info_to_file(rooms_info, filename="hotel_results.txt"):
    """将房间信息保存到文件"""
    if not rooms_info:
        log_step("没有房间信息可保存", "警告")
        return
    
    log_step(f"开始将房间信息保存到 {filename}")
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("============ 酒店房间信息 ============\n\n")
            
            # 添加酒店名称
            if "酒店名称" in rooms_info:
                f.write(f"酒店名称: {rooms_info['酒店名称']}\n\n")
            
            # 添加基本搜索信息
            f.write(f"搜索目的地: {Config.DESTINATION}\n")
            f.write(f"入住日期: {Config.CHECK_IN_DATE}\n")
            f.write(f"离店日期: {Config.CHECK_OUT_DATE}\n")
            f.write(f"入住时长: {(datetime.strptime(Config.CHECK_OUT_DATE, '%Y-%m-%d') - datetime.strptime(Config.CHECK_IN_DATE, '%Y-%m-%d')).days}晚\n\n")
            
            # 如果提取了酒店评分，添加到结果中
            hotel_score = None
            try:
                with open(Config.LOG_FILE, "r", encoding="utf-8") as log_file:
                    log_content = log_file.read()
                    # 从日志中提取评分信息
                    score_match = re.search(r'评分: ([0-9.]+)', log_content)
                    if score_match:
                        hotel_score = score_match.group(1)
                    
                    # 提取酒店地址
                    address_match = re.search(r'近瓦町站|地址[:：]([^,，\n]+)', log_content)
                    if address_match:
                        hotel_address = address_match.group(0)
                        f.write(f"酒店位置: {hotel_address}\n")
                    
                    # 提取酒店其他信息
                    points_match = re.search(r'"设备齐全[^"]+"', log_content)
                    if points_match:
                        hotel_points = points_match.group(0).replace('"', '')
                        f.write(f"酒店特点: {hotel_points}\n")
            except Exception as e:
                log_step(f"提取日志附加信息时出错: {str(e)}", "警告")
            
            if hotel_score:
                f.write(f"酒店评分: {hotel_score}\n")
            
            f.write("\n" + "="*40 + "\n\n")
            
            # 遍历房型列表
            for i, room in enumerate(rooms_info.get("房型列表", [])):
                f.write(f"房型 {i+1}: {room['房型名称']}\n")
                f.write(f"床型: {room['床型']}\n")
                f.write(f"面积和楼层: {room['面积和楼层']}\n")
                f.write("\n价格选项:\n")
                
                for j, offer in enumerate(room['价格选项']):
                    f.write(f"  选项 {j+1}:\n")
                    for key, value in offer.items():
                        f.write(f"    {key}: {value}\n")
                    f.write("\n")
                
                f.write("----------------------------------------\n\n")
                
        log_step(f"房间信息已保存到 {filename}", "成功")
        
    except Exception as e:
        log_step(f"保存房间信息到文件失败: {str(e)}", "失败")

# ==================== 主函数更新 ====================

async def main():
    """主函数"""
    log_step("程序开始运行")
    
    try:
        async with async_playwright() as p:
            # 加载cookies
            cookies = []
            if os.path.exists(Config.COOKIE_FILE):
                try:
                    with open(Config.COOKIE_FILE, 'r') as f:
                        cookies = json.load(f)
                    log_step(f"成功加载cookies, 共{len(cookies)}条", "成功")
                except Exception as e:
                    log_step(f"加载cookies失败: {str(e)}", "警告")
            
            # 启动浏览器
            browser = await p.chromium.launch(headless=Config.HEADLESS)
            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
            
            # 设置cookies
            if cookies:
                await context.add_cookies(cookies)
            
            # 打开页面
            page = await context.new_page()
            await page.goto('https://hotels.ctrip.com/', timeout=Config.TIMEOUT)
            
            log_step("成功打开携程酒店首页", "成功")
            if Config.SAVE_TEMP_FILES:
                await page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}home_page.png")
            
            # 第一部分：搜索酒店（保持原有代码）
            try:
                # 填写搜索参数
                await set_search_parameters(page)
                
                # 执行搜索
                await search_hotel(page)
                
                # 寻找目标酒店
                await find_target_hotel(page)
            except Exception as e:
                log_step(f"第一部分搜索酒店过程出错: {str(e)}", "失败")
                traceback.print_exc()
            
            # 第二部分：提取酒店列表信息并进入详情页
            try:
                hotel_list, target_hotel_card = await extract_hotel_list_info(page)
                
                # 仅在需要保存临时文件时保存JSON
                if Config.SAVE_TEMP_FILES:
                    # 保存酒店列表信息
                    with open("hotel_list.json", "w", encoding="utf-8") as f:
                        json.dump(hotel_list, f, ensure_ascii=False, indent=2)
                    log_step("酒店列表信息已保存到hotel_list.json", "成功")
                
                # 进入酒店详情页
                detail_page = await enter_hotel_detail(page, target_hotel_card)
                
                if not detail_page:
                    # 如果无法通过列表进入详情页，尝试直接访问已知URL
                    for url in Config.KNOWN_HOTEL_URLS:
                        log_step(f"尝试直接访问酒店URL: {url}", "信息")
                        detail_page = await context.new_page()
                        await detail_page.goto(url, timeout=Config.TIMEOUT)
                        
                        # 检查是否成功加载酒店详情页
                        try:
                            await detail_page.wait_for_selector('div.mainRoomList__UlISo, div.commonRoomCard__BpNjl', timeout=15000)
                            log_step(f"成功直接访问酒店详情页: {url}", "成功")
                            if Config.SAVE_TEMP_FILES:
                                await detail_page.screenshot(path=f"{Config.SCREENSHOT_PREFIX}direct_hotel_detail.png")
                            break
                        except Exception:
                            log_step(f"直接访问URL未找到房间列表: {url}", "警告")
                            await detail_page.close()
                            detail_page = None
                
                # 第三部分：提取酒店房间信息
                if detail_page:
                    rooms_info = await extract_room_info(detail_page)
                    
                    # 保存房间信息到文件
                    await save_room_info_to_file(rooms_info, Config.OUTPUT_FILE)
                    
                    # 仅在需要保存临时文件时保存JSON
                    if Config.SAVE_TEMP_FILES:
                        # 同时保存为JSON格式便于程序处理
                        with open("room_info.json", "w", encoding="utf-8") as f:
                            json.dump(rooms_info, f, ensure_ascii=False, indent=2)
                        log_step("房间信息已保存到room_info.json", "成功")
                else:
                    log_step("无法获取有效的酒店详情页，跳过房间信息提取", "失败")
                
            except Exception as e:
                log_step(f"第二/三部分处理过程出错: {str(e)}", "失败")
                traceback.print_exc()
            
            # 保存日志
            save_log_to_file(Config.LOG_FILE)
            
            # 关闭浏览器
            await browser.close()
            log_step("程序运行完成", "成功")
    
    except Exception as e:
        log_step(f"程序运行出错: {str(e)}", "失败")
        traceback.print_exc()
        save_log_to_file(Config.LOG_FILE)

if __name__ == "__main__":
    asyncio.run(main()) 