import streamlit as st
import pandas as pd
import math
import requests

# --- НАСТРОЙКИ ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 

st.set_page_config(layout="wide", page_title="Складской Терминал")

# 1. Загрузка данных
def load_initial_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            rows = []
            for item in data.get('rows', []):
                name = item.get('name', '')
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

# --- ИНИЦИАЛИЗАЦИЯ ---
if 'archive' not in st.session_state:
    st.session_state.archive = pd.DataFrame()

# Загружаем данные только если их нет в памяти
if 'df' not in st.session_state:
    st.session_state.df = load_initial_data()

st.title("📦 Система управления складом")

# Кнопка принудительного обновления в сайдбаре
if st.sidebar.button("🔄 Обновить из МойСклад"):
    st.session_state.df = load_initial_data()
    st.rerun()

# МЕТРИКИ (Скриншот a8eb536d)
if st.session_state.df is not None and not st.session_state.df.empty:
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16)
    c1, c2, c3 = st.columns(3)
    c1.metric("Всего коробов на складе", total_boxes)
    c2.metric("Расчетное кол-во паллетов", pallets)
    c3.metric("Стоимость хранения / сутки", f"{pallets * 50} ₽")

st.divider()

search_query = st.text_input("🔍 Поиск по Артикулу или Наименованию")
tab1, tab2, tab3 = st.tabs(["📦 Остатки ИП", "🏢 Остатки ООО", "📜 Архив отгрузок"])

def render_tab(storage_type, key_suffix):
    df_all = st.session_state.df
    if df_all is None or df_all.empty:
        st.info("Нет данных для отображения")
        return

    # Фильтруем данные для текущей вкладки
    filtered_df = df_all[df_all["Направление(склад)"] == storage_type].reset_index(drop=True)
    
    if search_query:
        sq = search_query.lower()
        filtered_df = filtered_df[
            filtered_df['Наименование'].str.lower().str.contains(sq) | 
            filtered_df['Артикул'].astype(str).str.lower().str.contains(sq)
        ]

    st.subheader(f"Остатки {storage_type}")
    
    # Таблица с мульти-выбором (как на видео 1000011581)
    event = st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key=f"table_{key_suffix}"
    )
    qty_to_ship = st.number_input("Количество для отгрузки", min_value=1, value=1, key=f"qty_input_{key_suffix}")

    # Исправленная кнопка отгрузки
    if st.button(f"🚀 ОТГРУЗИТЬ ВЫБРАННОЕ ({storage_type})", key=f"btn_ship_{key_suffix}"):
        selected_indices = event.get("selection", {}).get("rows", [])
        
        if selected_indices:
            ids_to_remove = []
            for idx in selected_indices:
                item = filtered_df.iloc[idx].copy()
                
                # 1. Списание через API
                create_ms_loss(item['uuid'], qty_to_ship)
                
                # 2. Перенос в архив
                item['Отгружено'] = qty_to_ship
                st.session_state.archive = pd.concat([st.session_state.archive, pd.DataFrame([item])], ignore_index=True)
                
                # Сохраняем ID для удаления
                ids_to_remove.append(item['uuid'])
            
            # 3. УДАЛЕНИЕ ИЗ ПАМЯТИ (чтобы исчезло из списка)
            st.session_state.df = st.session_state.df[~st.session_state.df['uuid'].isin(ids_to_remove)].reset_index(drop=True)
            
            st.success("Отгрузка выполнена!")
            st.rerun()
        else:
            st.error("Ничего не выбрано!")

with tab1: render_tab("ИП", "ip")
with tab2: render_tab("ООО", "ooo")
with tab3:
    st.subheader("📜 Архив отгрузок")
    if not st.session_state.archive.empty:
        st.dataframe(st.session_state.archive, use_container_width=True, hide_index=True)
        if st.button("🗑 Очистить архив"):
            st.session_state.archive = pd.DataFrame()
            st.rerun()


