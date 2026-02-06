import streamlit as st
import pandas as pd
import math
import requests

# --- НАСТРОЙКИ (Впиши свои данные) ---
TOKEN = "bdcc5b722dd8bad73b205be6fff08267da7c121a"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал")

# 1. Загрузка данных из МойСклад
def load_initial_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            rows = []
            for item in data.get('rows', []):
                rows.append({
                    "uuid": item.get('id'),
                    "Наименование": item.get('name'),
                    "Артикул": item.get('article', ''),
                    "Баркод товара(штрихкод)": item.get('code', ''),
                    "Кол-во": item.get('stock', 0),
                    "Направление(склад)": "ИП" if "ИП" in item.get('name', '') else "ООО"
                })
            return pd.DataFrame(rows)
    except:
        pass
    return pd.DataFrame()

# 2. Функция списания
def create_ms_loss(product_id, quantity):
    url = "https://api.moysklad.ru/api/remap/1.2/entity/loss"
    data = {
        "organization": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/organization/{ORG_ID}", "type": "organization", "mediaType": "application/json"}},
        "store": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}", "type": "store", "mediaType": "application/json"}},
        "positions": [{"quantity": float(quantity), "assortment": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id}", "type": "product", "mediaType": "application/json"}}}]
    }
    try:
        res = requests.post(url, headers=HEADERS, json=data)
        return res.status_code == 201
    except:
        return False

# --- ИНИЦИАЛИЗАЦИЯ (Работаем с памятью) ---
if 'archive' not in st.session_state:
    st.session_state.archive = pd.DataFrame()

if 'df' not in st.session_state:
    st.session_state.df = load_initial_data()

# --- ИНТЕРФЕЙС (ТОЧЬ-В-ТОЧЬ КАК НА СКРИНШОТАХ) ---
st.title("📦 Система управления складом (ОНЛАЙН)")

# МЕТРИКИ (Скриншот 1000011681)
if not st.session_state.df.empty:
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16)
    c1, c2, c3 = st.columns(3)
    c1.metric("Всего коробов на складе", total_boxes)
    c2.metric("Расчетное кол-во паллетов", pallets)
    c3.metric("Стоимость хранения / сутки", f"{pallets * 50} ₽")

st.divider()

# ПОИСК И ВКЛАДКИ
search_query = st.text_input("🔍 Поиск по Баркоду, Артикулу или Наименованию")
tab1, tab2, tab3 = st.tabs(["📦 Остатки ИП", "🏢 Остатки ООО", "📜 Архив отгрузок"])

def render_tab(storage_type, key_suffix):
    df = st.session_state.df
    if df.empty:
        st.info("Остатки пусты")
        return

    # Фильтрация данных
    filtered_df = df[df["Направление(склад)"].str.contains(storage_type, na=False)]
    if search_query:
        sq = search_query.lower()
        filtered_df = filtered_df[
            filtered_df['Баркод товара(штрихкод)'].astype(str).str.contains(sq) |
            filtered_df['Артикул'].astype(str).str.contains(sq) |
            filtered_df['Наименование'].str.lower().str.contains(sq)
        ]

    # Вывод списка товаров как на скриншоте 1000011682
    for index, row in filtered_df.iterrows():
        with st.container():
            col_info, col_btn = st.columns([0.8, 0.2])
            with col_info:
                st.write(f"{row['Наименование']}")
                st.write(f"Артикул: {row['Артикул']} | Баркод: {row['Баркод товара(штрихкод)']}")
                st.write(f"Остаток в МС: {row['Кол-во']} шт.")
                with col_btn:
                qty = st.number_input("Кол-во", min_value=1, value=1, key=f"q_{key_suffix}_{index}")
                if st.button("🚀 ОТГРУЗИТЬ", key=f"btn_{key_suffix}_{index}"):
                    # 1. Списываем в МойСклад
                    create_ms_loss(row['uuid'], qty)
                    
                    # 2. Добавляем в архив
                    item_archived = row.copy()
                    item_archived['Отгружено'] = qty
                    st.session_state.archive = pd.concat([st.session_state.archive, pd.DataFrame([item_archived])], ignore_index=True)
                    
                    # 3. Удаляем из текущих остатков в памяти (чтобы исчез)
                    st.session_state.df = st.session_state.df[st.session_state.df['uuid'] != row['uuid']].reset_index(drop=True)
                    
                    st.success(f"Отгружено: {row['Артикул']}")
                    st.rerun()
            st.divider()

with tab1: render_tab("ИП", "ИП")
with tab2: render_tab("ООО", "ООО")
with tab3:
    st.subheader("📜 Архив отгрузок")
    if not st.session_state.archive.empty:
        st.dataframe(st.session_state.archive, use_container_width=True, hide_index=True)
        if st.button("🗑 Очистить архив"):
            st.session_state.archive = pd.DataFrame()
            st.rerun()
    else:
        st.info("Архив пуст")




