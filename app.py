import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime
import io

# --- ТВОИ ДАННЫЕ ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал МС")

def load_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all?limit=1000"
    try:
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            rows = []
            for i in res.json().get('rows', []):
                name = i.get('name', '')
                rows.append({
                    "uuid": str(i.get('id')),
                    "Наименование": name,
                    "Артикул": str(i.get('article', '—')),
                    "Баркод": str(i.get('code', '—')),
                    "Кол-во": i.get('stock', 0),
                    "Номер короба": "МС",
                    "Тип": "ИП" if "ИП" in name.upper() else "ООО"
                })
            return pd.DataFrame(rows)
    except: pass
    return pd.DataFrame()

if 'df' not in st.session_state: st.session_state.df = load_data()
if 'arch' not in st.session_state: 
    st.session_state.arch = pd.DataFrame(columns=["uuid", "Наименование", "Артикул", "Баркод", "Кол-во", "Номер короба", "Тип"])

st.title("📦 Система управления складом")

# Кнопка обновления
if st.button("🔄 Обновить остатки из МойСклад", use_container_width=True):
    fresh_df = load_data()
    if not st.session_state.arch.empty:
        arch_ids = st.session_state.arch['uuid'].tolist()
        st.session_state.df = fresh_df[~fresh_df['uuid'].isin(arch_ids)].reset_index(drop=True)
    else:
        st.session_state.df = fresh_df
    st.rerun()

search = st.text_input("🔍 Поиск (Баркод / Артикул / Название)")

t1, t2, t3, t4, t5 = st.tabs(["📦 ИП", "🏢 ООО", "📜 Архив отгрузки", "💰 Хранение", "📊 Итого по Баркодам"])

def render_table(storage_type, key):
    # Работаем с копией, чтобы не портить основной df
    current_df = st.session_state.df.copy()
    filt = current_df[current_df["Тип"] == storage_type].reset_index(drop=True)
    
    if search:
        filt = filt[filt.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)].reset_index(drop=True)

    if filt.empty:
        st.info(f"На складе {storage_type} пусто")
        return

    # Таблица с выбором
    sel = st.dataframe(filt, use_container_width=True, hide_index=True, 
                       selection_mode="multi-row", on_select="rerun", key=f"table_{key}")
    
    selected_indices = sel.get("selection", {}).get("rows", [])
    
    if selected_indices:
        if st.button(f"🚀 Завершить и отгрузить ({storage_type})", key=f"btn_{key}"):
            # Выбираем товары по индексам из отфильтрованного списка
            shipped_items = filt.iloc[selected_indices].copy()
            
            # Добавляем в архив
            st.session_state.arch = pd.concat([st.session_state.arch, shipped_items], ignore_index=True)
            
            # Удаляем из основного df по UUID
            ids_to_remove = shipped_items['uuid'].tolist()
            st.session_state.df = st.session_state.df[~st.session_state.df['uuid'].isin(ids_to_remove)].reset_index(drop=True)
            st.rerun()

with t1: render_table("ИП", "ip")
with t2: render_table("ООО", "ooo")

with t3:
    if not st.session_state.arch.empty:
        st.dataframe(st.session_state.arch, use_container_width=True, hide_index=True)
        
        # Генерация Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            out_df = st.session_state.arch[["Баркод", "Кол-во", "Номер короба"]].copy()
            out_df["Дата приемки"] = ""
            out_df["ФИО сотрудника"] = ""
            out_df.to_excel(writer, index=False, sheet_name='Отгрузка')
        
        st.download_button("📥 Завершить и скачать Excel", output.getvalue(), "postavka.xlsx", use_container_width=True)
        
        if st.button("⏪ Вернуть всё на склад"):
            st.session_state.df = pd.concat([st.session_state.df, st.session_state.arch], ignore_index=True)
            st.session_state.arch = st.session_state.arch.iloc[0:0]
            st.rerun()
    else: st.info("Архив пуст")

with t4:
    total_qty = int(st.session_state.df["Кол-во"].sum()) if not st.session_state.df.empty else 0
    pallets = math.ceil(total_qty / 16) if total_qty > 0 else 0
    st.metric("Коробов на остатке", total_qty)
    st.metric("Стоимость хранения (сутки)", f"{pallets * 50} руб")

with t5:
    if not st.session_state.df.empty:
        summary = st.session_state.df.groupby("Баркод")["Кол-во"].sum().reset_index()
        st.dataframe(summary, use_container_width=True, hide_index=True)



