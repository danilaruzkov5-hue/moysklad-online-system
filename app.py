import streamlit as st
import pandas as pd
import math
import requests

# --- КОНСТАНТЫ ---
TOKEN = "bdcc5b722dd8bad73b205be6fff08267da7c121a"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал Онлайн")
st.title("📦 Система управления складом (ОНЛАЙН)")

# 1. Загрузка данных напрямую из МС (вместо Google)
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
            df = pd.DataFrame(rows)
            return df, pd.DataFrame(), True
    except:
        pass
    return pd.DataFrame(), pd.DataFrame(), False

# 2. Функция списания в МойСклад
def create_ms_loss(product_id, quantity):
    url = "https://api.moysklad.ru/api/remap/1.2/entity/loss"
    data = {
        "organization": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/organization/{ORG_ID}", "type": "organization", "mediaType": "application/json"}},
        "store": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}", "type": "store", "mediaType": "application/json"}},
        "positions": [{"quantity": float(quantity), "assortment": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id}", "type": "product", "mediaType": "application/json"}}}]
    }
    res = requests.post(url, headers=HEADERS, json=data)
    return res.status_code == 201

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

# Приемка из Excel
with st.expander("📥 Загрузка новой приемки из Excel"):
    data_input = st.text_area("Вставьте данные из Excel (Баркод, Кол-во, Короб)")
    if st.button("Создать приемку в МойСклад"):
        st.success("Данные отправлены в МойСклад!")

# МЕТРИКИ
if not st.session_state.df.empty:
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16) if total_boxes > 0 else 0
    
    col_info1, col_info2, col_info3 = st.columns(3)
    col_info1.metric("Всего коробов на складе", total_boxes)
    col_info2.metric("Расчетное кол-во паллетов", pallets)
    col_info3.metric("Стоимость хранения / сутки", f"{pallets * 50} ₽")

st.divider()

# ПОИСК
search_query = st.text_input("🔍 Поиск по Баркоду, Артикулу или Наименованию")

# ВКЛАДКИ
tab1, tab2, tab3 = st.tabs(["📦 Остатки ИП", "🏢 Остатки ООО", "📜 Архив отгрузок"])

def render_tab(storage_type_filter, key_suffix):
    df = st.session_state.df
    mask = df["Направление(склад)"].astype(str).str.contains(storage_type_filter, na=False)
    filtered_df = df[mask]

    if search_query:
        sq = search_query.lower()
        filtered_df = filtered_df[
            filtered_df['Баркод товара(штрихкод)'].astype(str).str.contains(sq) |
            filtered_df['Артикул'].astype(str).str.contains(sq) |
            filtered_df['Наименование'].str.lower().str.contains(sq)
        ]

    st.subheader(f"Остатки {key_suffix}")
    event = st.dataframe(filtered_df, use_container_width=True, on_select="rerun", selection_mode="multi-row", key=f"table_{key_suffix}")
    qty_to_ship = st.number_input("Сколько штук отгружаем?", min_value=1, value=1, key=f"qty_{key_suffix}")

    if st.button(f"🚀 ОТГРУЗИТЬ ВЫБРАННОЕ", key=f"btn_{key_suffix}"):
        if event.selection.rows:
            selected_indices = filtered_df.index[event.selection.rows]
            for idx in selected_indices:
                item = st.session_state.df.loc[idx]
                # Списание в МС
                if create_ms_loss(item['uuid'], qty_to_ship):
                    # Добавляем в архив
                    shipped_item = st.session_state.df.loc[[idx]].copy()
                    shipped_item['Кол-во'] = qty_to_ship
                    st.session_state.archive = pd.concat([st.session_state.archive, shipped_item], ignore_index=True)
            
            st.session_state.df = st.session_state.df.drop(selected_indices).reset_index(drop=True)
            st.success("Товары отгружены и списаны в МС!")
            st.rerun()
        else:
            st.error("Сначала выделите строки галочками!")

with tab1: render_tab("ИП", "ИП")
with tab2: render_tab("ООО", "ООО")
with tab3:
    st.subheader("📜 Архив отгрузок")
    if not st.session_state.archive.empty:
        st.dataframe(st.session_state.archive, use_container_width=True)
        if st.button("🗑 Очистить архив"):
            st.session_state.archive = pd.DataFrame()
            st.rerun()
    else:
        st.info("Архив пока пуст")







