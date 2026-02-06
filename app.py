import streamlit as st
import pandas as pd
import math
import requests

# --- КОНСТАНТЫ (ПРОВЕРЬ ИХ ЕЩЕ РАЗ) ---
TOKEN = "bdcc5b722dd8bad73b205be6fff08267da7c121a"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал")

# 1. Функция загрузки с проверкой ошибок
def load_initial_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            rows = []
            for item in data.get('rows', []):
                name = item.get('name', '')
                # Если в названии нет ИП/ООО, по умолчанию кидаем в ИП, чтобы данные не пропадали
                direction = "ООО" if "ООО" in name else "ИП"
                rows.append({
                    "uuid": item.get('id'),
                    "Наименование": name,
                    "Артикул": item.get('article', ''),
                    "Баркод товара(штрихкод)": item.get('code', ''),
                    "Кол-во": item.get('stock', 0),
                    "Направление(склад)": direction
                })
            return pd.DataFrame(rows)
        else:
            st.error(f"Ошибка API МойСклад: {response.status_code}. Проверь токен.")
    except Exception as e:
        st.error(f"Не удалось подключиться: {e}")
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

# --- ИНИЦИАЛИЗАЦИЯ ---
if 'archive' not in st.session_state:
    st.session_state.archive = pd.DataFrame()

if 'df' not in st.session_state or st.sidebar.button("🔄 ОБНОВИТЬ ДАННЫЕ"):
    st.session_state.df = load_initial_data()

st.title("📦 Система управления складом")

# Проверка: если данных совсем нет
if st.session_state.df is None or st.session_state.df.empty:
    st.warning("⚠️ Данные не найдены. Проверь токен и остатки в МойСклад.")
    if st.button("Попробовать загрузить снова"):
        st.session_state.df = load_initial_data()
        st.rerun()
else:
    # МЕТРИКИ
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16)
    c1, c2, c3 = st.columns(3)
    c1.metric("Всего коробов", total_boxes)
    c2.metric("Паллетов", pallets)
    c3.metric("Хранение / сутки", f"{pallets * 50} ₽")

    st.divider()
    search_query = st.text_input("🔍 Поиск по артикулу или названию")
    tab1, tab2, tab3 = st.tabs(["📦 ИП", "🏢 ООО", "📜 Архив"])

    def render_tab(storage_type, key_suffix):
        df = st.session_state.df
        filtered_df = df[df["Направление(склад)"] == storage_type].reset_index(drop=True)

        if search_query:
            sq = search_query.lower()
            filtered_df = filtered_df[
                filtered_df['Артикул'].astype(str).str.lower().contains(sq) |
                filtered_df['Наименование'].str.lower().contains(sq)
            ]

        if filtered_df.empty:
            st.info(f"На складе {storage_type} сейчас пусто.")
            return

        event = st.dataframe(filtered_df, use_container_width=True, hide_index=True, selection_mode="multi-row", on_select="rerun", key=f"t_{key_suffix}")
        
        qty = st.number_input("Кол-во", min_value=1, value=1, key=f"q_{key_suffix}")
        if st.button(f"🚀 ОТГРУЗИТЬ", key=f"b_{key_suffix}"):
            selected_rows = event.get("selection", {}).get("rows", [])
            if selected_rows:
                for row_idx in selected_rows:
                    item = filtered_df.iloc[row_idx].copy()
                    create_ms_loss(item['uuid'], qty)
                    item['Кол-во'] = qty
                    st.session_state.archive = pd.concat([st.session_state.archive, pd.DataFrame([item])], ignore_index=True)
                    st.session_state.df = st.session_state.df[st.session_state.df['uuid'] != item['uuid']].reset_index(drop=True)
                st.success("Отгружено!")
                st.rerun()
            else:
                st.error("Выдели строки галочками!")

    with tab1: render_tab("ИП", "ИП")
    with tab2: render_tab("ООО", "ООО")
    with tab3:
        st.subheader("📜 Архив")
        st.dataframe(st.session_state.archive, use_container_width=True, hide_index=True)



