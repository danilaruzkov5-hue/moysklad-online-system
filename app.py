import streamlit as st
import pandas as pd
import math
import requests
from datetime import datetime

# --- НАСТРОЙКИ ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал")

# 1. Загрузка данных из МойСклад (с учетом штрихкодов)
def load_moysklad_data():
    # Добавляем limit=1000, чтобы точно забрать все товары разом
    url = "https://api.moysklad.ru/api/remap/1.2/entity/product?limit=1000"
    try:
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            products = []
            rows = res.json().get('rows', [])
            
            for i in rows:
                # 1. Извлекаем Штрихкод (EAN13)
                barcodes = i.get('barcodes', [])
                barcode_value = barcodes[0].get('ean13') if barcodes else ""
                
                # 2. Извлекаем Код (который на скриншоте 2036964984)
                # В API он называется 'code'
                external_code = i.get('code', '')
                
                products.append({
                    "uuid": i.get('id'),
                    "Артикул": i.get('article', ''), # Если пусто, будет пустая строка
                    "Баркод": str(barcode_value) if barcode_value else str(external_code),
                    "Наименование": i.get('name', ''),
                })
            
            df = pd.DataFrame(products)
            # Принудительно очищаем строки от пробелов
            df['Баркод'] = df['Баркод'].astype(str).str.strip()
            return df
        else:
            st.error(f"Ошибка API: {res.status_code}")
    except Exception as e:
        st.error(f"Связь прервана: {e}")
    return pd.DataFrame()

# 2. Инициализация состояний
if 'db' not in st.session_state: st.session_state.db = load_moysklad_data()
if 'stock' not in st.session_state: st.session_state.stock = pd.DataFrame(columns=["Баркод", "Артикул", "Кол-во", "Номер короба", "Тип"])
if 'archive' not in st.session_state: st.session_state.archive = pd.DataFrame()

st.title("📦 Управление складом")

# --- СЕКЦИЯ ПРИЕМКИ (EXCEL) ---
with st.sidebar:
    st.header("📥 Приемка товара")
    uploaded_file = st.file_uploader("Загрузи Excel (A-Баркод, B-Кол-во, C-Короб)", type="xlsx")
    entity_type = st.radio("Тип поставки:", ["ИП", "ООО"])
    
    if uploaded_file and st.button("Загрузить в систему"):
        new_data = pd.read_excel(uploaded_file, names=["Баркод", "Кол-во", "Номер короба"])
        new_data["Баркод"] = new_data["Баркод"].astype(str)
        # Сопоставляем с базой МС для получения артикула
        db = st.session_state.db
        new_data = new_data.merge(db[['Баркод', 'Артикул']], on="Баркод", how="left")
        new_data["Тип"] = entity_type
        st.session_state.stock = pd.concat([st.session_state.stock, new_data], ignore_index=True)
        st.success("Принято!")

# --- ОСНОВНОЙ ИНТЕРФЕЙС ---
search = st.text_input("🔍 Поиск по Баркоду или Артикулу")

tab_ip, tab_ooo, tab_arch, tab_calc = st.tabs(["🏢 ИП", "🏢 ООО", "📜 Архив отгрузок", "💰 Хранение"])

def process_shipping(df_subset, storage_type):
    if df_subset.empty:
        return st.info("На складе пусто")
    
    if search:
        df_subset = df_subset[(df_subset['Баркод'].str.contains(search)) | (df_subset['Артикул'].str.contains(search))]

    # Выбор коробов
    selected_indices = st.multiselect("Выбери короба для отгрузки:", df_subset.index, 
                                      format_func=lambda x: f"Короб №{df_subset.loc[x, 'Номер короба']} | {df_subset.loc[x, 'Артикул']} ({df_subset.loc[x, 'Кол-во']} шт)")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"🚀 Завершить отгрузку {storage_type}", use_container_width=True):
            if selected_indices:
                shipped_items = st.session_state.stock.loc[selected_indices].copy()
                shipped_items['Дата отгрузки'] = datetime.now().strftime("%d.%m.%Y %H:%M")
                
                # Добавляем в архив
                st.session_state.archive = pd.concat([st.session_state.archive, shipped_items], ignore_index=True)
                # Удаляем из остатков
                st.session_state.stock = st.session_state.stock.drop(selected_indices).reset_index(drop=True)
                st.success("Отгружено и добавлено в архив!")
                st.rerun()
    
    with col2:
        if st.button("❌ Вернуть/Удалить короб", use_container_width=True):
            st.warning("Выберите короба в списке и нажмите 'Завершить', они просто удалятся из текущего сеанса.")

    st.dataframe(df_subset, use_container_width=True)

with tab_ip:
    process_shipping(st.session_state.stock[st.session_state.stock["Тип"] == "ИП"], "ИП")

with tab_ooo:
    process_shipping(st.session_state.stock[st.session_state.stock["Тип"] == "ООО"], "ООО")

with tab_arch:
    if not st.session_state.archive.empty:
        st.dataframe(st.session_state.archive, use_container_width=True)
        csv = st.session_state.archive.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Скачать файл поставки для склада", csv, "postavka.csv", "text/csv")

with tab_calc:
    st.header("Подсчет хранения")
    total_boxes = len(st.session_state.stock)
    pallets = math.ceil(total_boxes / 16) if total_boxes > 0 else 0
    cost = pallets * 50
    st.metric("Коробов на складе", total_boxes)
    st.metric("Итого паллет", pallets)
    st.metric("Стоимость хранения в сутки", f"{cost} руб.")


