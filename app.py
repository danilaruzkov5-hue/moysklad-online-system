import streamlit as st
import pandas as pd
import requests
import math

# --- НАСТРОЙКИ (Впиши свои данные) ---
TOKEN = "bdcc5b722dd8bad73b205be6fff08267da7c121a"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" # Можно найти в ссылке МС
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace"    # Можно найти в ссылке МС
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

st.set_page_config(page_title="Терминал Отгрузки", layout="wide")

# Стиль как на скриншотах
st.markdown("""
    <style>
    .main { background-color: #f5f5f5; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    </style>
    """, unsafe_allow_html=True)

# 1. Загрузка данных из МойСклад
def load_ms_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            rows = []
            for item in data.get('rows', []):
                # Проверяем ИП или ООО по названию или доп. полю
                direction = "ИП" if "ИП" in item.get('name', '') else "ООО"
                rows.append({
                    "uuid": item.get('id'),
                    "Наименование": item.get('name'),
                    "Артикул": item.get('article', ''),
                    "Баркод": item.get('code', ''),
                    "Кол-во": item.get('stock', 0),
                    "Номер короба": item.get('code', '—'), # Используем код как номер короба, если нет спец. поля
                    "Направление": direction
                })
            return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Ошибка API: {e}")
    return pd.DataFrame()

# 2. Функция списания (Отгрузка)
def create_ms_loss(product_id, quantity):
    url = "https://api.moysklad.ru/api/remap/1.2/entity/loss"
    data = {
        "organization": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/organization/{ORG_ID}", "type": "organization", "mediaType": "application/json"}},
        "store": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}", "type": "store", "mediaType": "application/json"}},
        "positions": [{
            "quantity": float(quantity),
            "assortment": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id}", "type": "product", "mediaType": "application/json"}}
        }]
    }
    res = requests.post(url, headers=HEADERS, json=data)
    return res.status_code == 201

# --- ШАПКА САЙТА ---
col_logo, col_title = st.columns([1, 4])
with col_logo:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/Amazon_logo.svg/1024px-Amazon_logo.svg.png", width=100) # Замени на свой логотип
with col_title:
    st.title("ТЕРМИНАЛ ОТГРУЗКИ")

if 'df' not in st.session_state or st.sidebar.button("ОБНОВИТЬ ДАННЫЕ"):
    with st.spinner('Загрузка из МойСклад...'):
        st.session_state.df = load_ms_data()

# Поиск
search_query = st.text_input("🔍 Поиск по Артикулу или Наименованию", "").lower()

tab1, tab2 = st.tabs(["📦 ИП", "🏢 ООО"])

def render_tab(storage_type):
    df = st.session_state.df
    if df.empty:
        st.info("Данные не загружены")
        return

    # Фильтрация
    filtered_df = df[df["Направление"] == storage_type]
    if search_query:
        filtered_df = filtered_df[
            filtered_df['Артикул'].str.lower().str.contains(search_query) | 
            filtered_df['Наименование'].str.lower().str.contains(search_query)
        ]
    
    filtered_df = filtered_df.reset_index(drop=True)

    # Статистика (Паллеты и Хранение)
    unique_boxes = filtered_df['Номер короба'].nunique()
    pallets = math.ceil(unique_boxes / 16)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Всего коробов", unique_boxes)
    c2.metric("Паллетов", pallets)
    c3.metric("Хранение (сутки)", f"{pallets * 50} ₽")

    st.write("---")
    # Список товаров с чекбоксами
    selected_indices = []
    for i, row in filtered_df.iterrows():
        col_chk, col_txt = st.columns([0.1, 0.9])
        if col_chk.checkbox("", key=f"chk_{storage_type}_{i}"):
            selected_indices.append(i)
        col_txt.write(f"{row['Артикул']} | {row['Наименование']} | Остаток: {row['Кол-во']} (Короб: {row['Номер короба']})")

    st.write("---")
    
    qty_to_ship = st.number_input("Количество для отгрузки", min_value=1, value=1, key=f"q_{storage_type}")
    
    if st.button(f"ОТГРУЗИТЬ ВЫБРАННОЕ ({storage_type})"):
        if not selected_indices:
            st.warning("Выберите хотя бы один товар!")
        else:
            success_count = 0
            for idx in selected_indices:
                item = filtered_df.loc[idx]
                if create_ms_loss(item['uuid'], qty_to_ship):
                    success_count += 1
            
            st.success(f"Готово! Отгружено позиций: {success_count}")
            st.session_state.df = load_ms_data() # Обновляем остатки
            st.rerun()

with tab1: render_tab("ИП")
with tab2: render_tab("ООО")








