import streamlit as st
import pandas as pd
import math
import requests
import os

# --- КОНСТАНТЫ ---
TOKEN = "bdcc5b722dd8bad73b205be6fff08267da7c121a"
SHEET_ID = "1uF7RvQUIylmGDaco1nDhZo2GSU1OOeos511K5xqZY3w"
# Ссылка для чтения данных из твоей Google Таблицы в формате CSV
STOCK_URL = https://script.google.com/macros/s/AKfycbwy0HjIVRjXwfvbHYEGKqu0jj7JckFfTzkfeCV5fxC1dEp2Lj9XuybQQ5lcCTAKVr6PYw/exec

st.set_page_config(layout="wide", page_title="Складской Терминал Онлайн")
st.title("📂 Система управления складом (ОНЛАЙН)")

def save_data(item_data=None):
    if item_data:
        script_url = "https://script.google.com/macros/s/AKfycbwehMYINOBcn4vJbEYB0ovpCRpNYjuWeVjRgtHJ7-sSeLLtJxhEbn2Dd6YZAC6mPQ8z0A/exec"
        try:
            import requests
            requests.post(script_url, json=item_data)
        except:
            pass

@st.cache_data(ttl=10) # Обновлять данные из Google Таблицы каждые 10 секунд
def load_initial_data():
    try:
        # 1. Проверка связи с API МойСклад
        url = "https://api.moysklad.ru/api/remap/1.2/entity/product"
        headers = {"Authorization": f"Bearer {TOKEN}"}
        response = requests.get(url, headers=headers, params={"limit": 1})
        api_status = response.status_code == 200
    except:
        api_status = False

    try:
        # 2. Загрузка остатков напрямую из Google Таблицы (вместо STOCK_FILE)
        df = pd.read_csv(STOCK_URL)
        # 3. Создаем пустой архив (вместо ARCHIVE_FILE)
        archive = pd.DataFrame()
        
        if not df.empty:
            df['Направление(склад)'] = df['Направление(склад)'].fillna('ИП')
            if 'Артикул' not in df.columns:
                df['Артикул'] = "Арт-" + df['Баркод товара(штрихкод)'].astype(str).str[-4:]
        
        return df, archive, api_status
    except Exception as e:
        st.error(f"Ошибка загрузки данных из облака: {e}")
        return pd.DataFrame(), pd.DataFrame(), api_status

# --- ИНИЦИАЛИЗАЦИЯ ---
if 'df' not in st.session_state:
    df, archive, status = load_initial_data()
    st.session_state.df = df
    st.session_state.archive = archive
    st.session_state.api_connected = status

# Индикатор связи
if st.session_state.api_connected:
    st.success("🟢 Связь с МойСклад установлена")
else:
    st.warning("🟡 Работа в автономном режиме")

# --- МЕТРИКИ ---
if not st.session_state.df.empty:
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16) if total_boxes > 0 else 0
    daily_cost = pallets * 50
    col_info1, col_info2, col_info3 = st.columns(3)
    col_info1.metric("Всего коробов на складе", total_boxes)
    col_info2.metric("Расчетное кол-во паллетов", pallets)
    col_info3.metric("Стоимость хранения / сутки", f"{daily_cost} ₽")

st.divider()

# --- ПОИСК ---
search_query = st.text_input("🔍 Поиск по Баркоду, Артикулу или Наименованию")
sq = search_query 

# --- ВКЛАДКИ ---
tab1, tab2, tab3 = st.tabs(["📊 Остатки ИП", "🏢 Остатки ООО", "📦 Архив отгрузок"])

def render_tab(storage_type_filter, key_suffix):
    # Фильтруем данные для отображения
    mask = st.session_state.df['Направление(склад)'].str.contains(storage_type_filter, na=False)
    filtered_df = st.session_state.df[mask]
    
    if sq:
            filtered_df = filtered_df[
                filtered_df['Баркод товара(штрихкод)'].astype(str).str.contains(sq) |
                filtered_df['Артикул'].astype(str).str.contains(sq) |
                filtered_df['Наименование'].astype(str).str.contains(sq)
            ]
    st.subheader(f"Остатки {key_suffix}")
    if filtered_df.empty:
        st.info("В этой категории товаров нет")
        return

    # Отображаем таблицу
    event = st.dataframe(filtered_df, use_container_width=True, on_select="rerun", selection_mode="multi-row", key=f"table_{key_suffix}")
    
    # Логика отгрузки
# 1. Поле для выбора количества (добавь ПЕРЕД кнопкой)
    qty_to_ship = st.number_input("Сколько штук отгружаем?", min_value=1, value=1, key=f"qty_{key_suffix}")

    # 2. Твоя кнопка (оставляем как есть)
    if st.button(f"🚀 ОТГРУЗИТЬ ВЫБРАННЫЕ", key=f"btn_{key_suffix}"):
        if event.selection.rows:
            # Получаем индексы выбранных строк
            selected_indices = filtered_df.index[event.selection.rows]
            
            # Цикл для отправки каждой выбранной позиции в Google Таблицу
            for idx in selected_indices:
                item_to_send = st.session_state.df.loc[idx].to_dict()
                # ПОДМЕНЯЕМ количество на то, которое ты ввел в поле выше
                item_to_send['Кол-во'] = qty_to_ship 
                
                # Отправляем именно это количество в Google
                save_data(item_to_send)
            
# Создаем запись для архива
            shipped_items = st.session_state.df.loc[selected_indices].copy()
            
            # ВАЖНО: Мы заменяем старое общее количество на то, которое реально отгрузили
            shipped_items['Кол-во'] = qty_to_ship 
            
            # Добавляем в архив на сайте
            st.session_state.archive = pd.concat([st.session_state.archive, shipped_items], ignore_index=True)
            
            # Удаляем из основного списка (или уменьшаем количество)
            st.session_state.df = st.session_state.df.drop(selected_indices).reset_index(drop=True)
            
            st.rerun()
        else:
            st.error("Сначала выделите строки галочками!")

with tab1:
    render_tab('ИП|Не указано', "ИП")

with tab2:
    render_tab('ООО|Юр лицо', "ООО")

with tab3:
    st.subheader("📦 Архив отгрузок")
    if st.session_state.archive.empty:
        st.info("Архив пока пуст")
    else:
        arc_event = st.dataframe(st.session_state.archive, use_container_width=True, on_select="rerun", selection_mode="multi-row", key="arc_table")
        
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📥 Скачать отчет", st.session_state.archive.to_csv(index=False).encode('utf-8-sig'), "otgruzka.csv")
        with c2:
            if st.button("🔄 ВЕРНУТЬ НА СКЛАД"):
                if arc_event.selection.rows:
                    idx = arc_event.selection.rows
                    to_return = st.session_state.archive.iloc[idx]
                    st.session_state.df = pd.concat([st.session_state.df, to_return], ignore_index=True)
                    st.session_state.archive = st.session_state.archive.drop(st.session_state.archive.index[idx]).reset_index(drop=True)
                    save_data()
                    st.rerun()







