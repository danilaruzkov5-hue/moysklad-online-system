import streamlit as st
import pandas as pd
import math
import requests

# --- НАСТРОЙКИ ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал")

# 1. Функция загрузки
def load_initial_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            rows = []
            for item in data.get('rows', []):
                name = item.get('name', '')
                direction = "ООО" if "ООО" in name.upper() else "ИП"
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
    requests.post(url, headers=HEADERS, json=data)

# --- ИНИЦИАЛИЗАЦИЯ ---
if 'archive' not in st.session_state:
    st.session_state.archive = pd.DataFrame()

# Загружаем данные один раз, чтобы они не возвращались после отгрузки
if 'df' not in st.session_state:
    st.session_state.df = load_initial_data()

st.title("📦 Система управления складом")

# Сайдбар для обновления данных
if st.sidebar.button("🔄 ОБНОВИТЬ ИЗ МОЙСКЛАД"):
    st.session_state.df = load_initial_data()
    st.rerun()

# МЕТРИКИ (как на скриншотах)
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
    # Берем данные из памяти
    df_all = st.session_state.df
    if df_all is None or df_all.empty:
        st.warning("Нет данных. Нажмите 'Обновить' в боковом меню.")
        return

    # Фильтруем для текущей вкладки
    filtered_df = df_all[df_all["Направление(склад)"] == storage_type].reset_index(drop=True)
    
    if search_query:
        sq = search_query.lower()
        filtered_df = filtered_df[
            filtered_df['Наименование'].str.lower().str.contains(sq) | 
            filtered_df['Артикул'].astype(str).str.lower().str.contains(sq)
        ]

    if filtered_df.empty:
        st.info(f"На складе {storage_type} пусто.")
        return

    # Таблица (как на видео)
    event = st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key=f"table_{key_suffix}"
    )
    qty_to_ship = st.number_input("Количество для отгрузки", min_value=1, value=1, key=f"qty_{key_suffix}")

    # КНОПКА ОТГРУЗКИ
    if st.button(f"🚀 ОТГРУЗИТЬ ВЫБРАННОЕ ({storage_type})", key=f"btn_{key_suffix}"):
        selected_rows = event.get("selection", {}).get("rows", [])
        
        if selected_rows:
            ids_to_remove = []
            for idx in selected_rows:
                item = filtered_df.iloc[idx].copy()
                
                # 1. API запрос
                create_ms_loss(item['uuid'], qty_to_ship)
                
                # 2. Добавляем в архив
                item['Отгружено'] = qty_to_ship
                st.session_state.archive = pd.concat([st.session_state.archive, pd.DataFrame([item])], ignore_index=True)
                
                # 3. Сохраняем ID для удаления из общего списка
                ids_to_remove.append(item['uuid'])
            
            # САМАЯ ВАЖНАЯ ЧАСТЬ: Удаляем отгруженное из основной переменной
            st.session_state.df = st.session_state.df[~st.session_state.df['uuid'].isin(ids_to_remove)].reset_index(drop=True)
            
            st.success("Успешно отгружено!")
            st.rerun()
        else:
            st.error("Сначала выделите товар галочкой в таблице!")

with tab1: render_tab("ИП", "ip")
with tab2: render_tab("ООО", "ooo")
with tab3:
    st.subheader("📜 Архив отгрузок")
    if not st.session_state.archive.empty:
        st.dataframe(st.session_state.archive, use_container_width=True, hide_index=True)
    else:
        st.info("Архив пуст")


