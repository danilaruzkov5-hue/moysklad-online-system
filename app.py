import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime
import io
from sqlalchemy import create_engine, text

# --- НАСТРОЙКИ ---
TOKEN = st.secrets["MS_TOKEN"]
ORG_ID = st.secrets["MS_ORG_ID"]
STORE_ID = st.secrets["MS_STORE_ID"]
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# --- БАЗА ДАННЫХ ---
DB_URL = st.secrets.get("DB_URL", "sqlite:///warehouse.db")
engine = create_engine(DB_URL)

# --- ВСТАВЛЯЙ ПРЯМО СЮДА ---
def check_and_log_daily():
    now = datetime.now()
    # Если время 23:00 или больше
    if now.hour >= 23:
        today_str = now.strftime("%Y-%m-%d")
        with engine.connect() as conn:
            # Проверяем, была ли запись
            res = conn.execute(text("SELECT 1 FROM daily_storage_logs WHERE log_date = :d"), {"d": today_str}).fetchone()

            if not res:
                # Если нет — считаем и записываем
                df = pd.read_sql(text("SELECT * FROM stock"), engine)
                b_ip = len(df[df['type'] == 'ИП'])
                b_ooo = len(df[df['type'] == 'ООО'])

                # 16 кор = 1 паллет
                p_ip = math.ceil(b_ip / 16)
                p_ooo = math.ceil(b_ooo / 16)

                # Записываем в базу
                conn.execute(text('''INSERT INTO daily_storage_logs
                VALUES (:d, :bi, :pi, :ci, :bo, :po, :co, :itb, :itp, :itc)'''),
                {"d": today_str, "bi": b_ip, "pi": p_ip, "ci": p_ip*50,
                 "bo": b_ooo, "po": p_ooo, "co": p_ooo*50,
                 "tb": b_ip+b_ooo, "tp": p_ip+p_ooo, "tc": (p_ip+p_ooo)*50})
                conn.commit()

# Обязательно запускаем эту функцию!
check_and_log_daily()
# -------------------------

def init_db():
    with engine.connect() as conn:
        conn.execute(text('''CREATE TABLE IF NOT EXISTS stock
            (uuid TEXT PRIMARY KEY, name TEXT, article TEXT, barcode TEXT, quantity REAL, box_num TEXT, type TEXT)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS archive
            (uuid TEXT PRIMARY KEY, name TEXT, article TEXT, barcode TEXT, quantity REAL, box_num TEXT, type TEXT, ship_date TEXT)'''))
        conn.commit()

init_db()

if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

def reset_selection():
    st.session_state.reset_counter += 1

st.set_page_config(layout="wide", page_title="Складской Терминал")

def load_api_data():
    url = f"https://api.moysklad.ru/api/remap/1.2/report/stock/all?limit=1000&filter=store=https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}"
    try:
        res = requests.get(url, headers=HEADERS)
        return res.json().get('rows', []) if res.status_code == 200 else []
    except: return []

ms_rows = load_api_data()
api_status = "🟢 Связь с МойСклад: Установлена" if ms_rows else "🟠 Связь с МойСклад: Ошибка"

st.title("📦 Единая база склада (ИП / ООО)")
st.caption(api_status)

# --- ПРИЕМКА ТОВАРА ---
with st.sidebar:
    st.header("📥 Приемка")
    uploaded_file = st.file_uploader("Загрузи Excel (Баркод, Кол-во, Короб)", type=["xlsx"])
    target_type = st.radio("Тип поставки:", ["ИП", "ООО"])

    if uploaded_file and st.button("➕ Добавить на баланс"):
        try:
            new_data = pd.read_excel(uploaded_file)
            new_data.columns = ["Баркод", "Кол-во", "Номер короба"]
            mapping = {str(r.get('code')): (r.get('article', '-'), r.get('name', 'Неизвестно')) for r in ms_rows}
            with engine.connect() as conn:
                for _, row in new_data.iterrows():
                    art, name = mapping.get(str(row["Баркод"]), ("-", "Новый товар"))
                    uid = f"{datetime.now().timestamp()}_{row['Баркод']}_{_}"
                    conn.execute(text("INSERT INTO stock VALUES (:u, :n, :a, :b, :q, :bn, :t)"),
                                 {"u":str(uid), "n":str(name), "a":str(art), "b":str(row["Баркод"]),
                                 "q":float(row["Кол-во"]), "bn":str(row["Номер короба"]), "t":str(target_type)})
                conn.commit()
            reset_selection()
            st.success("Данные сохранены!")
            st.rerun()
        except Exception as e: st.error(f"Ошибка: {e}")

search = st.text_input("🔍 Быстрый поиск (Баркод / Артикул / Короб)")
t1, t2, t3, t4, t5 = st.tabs(["🏠 ИП", "🏢 ООО", "📦 Архив", "📊 Хранение", "🧾 Итого"])

def render_table(storage_type, key):
    # Хранилище для накопленных UUID
    selection_key = f"selected_uuids_{key}"
    if selection_key not in st.session_state:
        st.session_state[selection_key] = set()

    # Загружаем данные из БД
    df = pd.read_sql(text(f"SELECT * FROM stock WHERE type='{storage_type}'"), engine)
    
    if df.empty:
        st.info(f"Склад {storage_type} пуст")
        return

    # Фильтрация по поиску
    df_display = df.copy()
    if search:
        mask = df_display.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
        df_display = df_display[mask]

    # --- ЛОГИКА СОХРАНЕНИЯ ГАЛОЧЕК ---
    # Находим индексы строк в ТЕКУЩЕМ отображении, которые уже были выбраны ранее
    current_selected_rows = [
        i for i, row in enumerate(df_display.itertuples()) 
        if row.uuid in st.session_state[selection_key]
    ]

    table_key = f"table_{key}_{st.session_state.reset_counter}"

    # Рендерим таблицу
    sel = st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        key=table_key,
        initial_selection={"rows": current_selected_rows} # Возвращаем галочки на место
    )

    # Синхронизация: что пользователь нажал прямо сейчас
    new_selected_indices = sel.get("selection", {}).get("rows", [])
    new_selected_uuids = set(df_display.iloc[new_selected_indices]['uuid'])
    
    # UUID всех строк, которые сейчас видны в таблице (с учетом поиска)
    visible_uuids = set(df_display['uuid'])

    # Обновляем глобальный выбор в session_state
    for uuid in visible_uuids:
        if uuid in new_selected_uuids:
            st.session_state[selection_key].add(uuid)
        else:
            st.session_state[selection_key].discard(uuid)

    # Итоговый список для действий
    final_selected_uuids = list(st.session_state[selection_key])

    if final_selected_uuids:
        # Фильтруем основной df по накопленным UUID (включая те, что не видны из-за поиска)
        selected_df = df[df['uuid'].isin(final_selected_uuids)]
        count = len(selected_df)

        if count > 0:
            st.write(f"### Выбрано товаров: {count}")
            c1, c2 = st.columns(2)

            # Подготовка Excel
            exp_df = selected_df[['barcode', 'quantity', 'box_num']].copy()
            exp_df.columns = ["Баркод", "Кол-во", "Номер короба"]
            exp_df["ШК"] = ""
            exp_df["Склад"] = storage_type

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                exp_df.to_excel(writer, index=False, sheet_name='Отгрузка')
            
            # Кнопка Отгрузить
            if c1.download_button(f"📦 Отгрузить ({count})", data=output.getvalue(), file_name=f"shipment_{storage_type}.xlsx", key=f"dl_{key}"):
                with engine.connect() as conn:
                    for uuid in final_selected_uuids:
                        conn.execute(text("INSERT INTO archive SELECT *, :d FROM stock WHERE uuid=:u"), {"d": datetime.now().strftime("%d.%m %H:%M"), "u": uuid})
                        conn.execute(text("DELETE FROM stock WHERE uuid=:u"), {"u": uuid})
                    conn.commit()
                st.session_state[selection_key] = set()
                reset_selection()
                st.rerun()

            # Кнопка Удалить
            if c2.button(f"🗑️ Удалить ({count})", key=f"del_btn_{key}"):
                with engine.connect() as conn:
                    for uuid in final_selected_uuids:
                        conn.execute(text("DELETE FROM stock WHERE uuid=:u"), {"u": uuid})
                    conn.commit()
                st.session_state[selection_key] = set()
                reset_selection()
                st.rerun()
                if search:
                    st.info(f"💡 Всего выбрано (включая другие поиски): {count}")
    else:
        st.info(f"Склад {storage_type} пуст")

with t1: render_table("ИП", "ip")
with t2: render_table("ООО", "ooo")

with t3:
    arch_type = st.radio("Архив:", ["ИП", "ООО"], horizontal=True, key="arch_sel")
    df_arch = pd.read_sql(text(f"SELECT * FROM archive WHERE type='{arch_type}'"), engine)

    if not df_arch.empty:
        arch_table_key = f"arch_table_{arch_type}_{st.session_state.reset_counter}"
        sel_a = st.dataframe(df_arch, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key=arch_table_key)

        # Экспорт всего архива
        output_a = io.BytesIO()
        with pd.ExcelWriter(output_a, engine='xlsxwriter') as writer:
            df_arch.to_excel(writer, index=False, sheet_name='Архив')
        st.download_button(f"📥 Скачать архив {arch_type}", output_a.getvalue(), f"archive_{arch_type}.xlsx")

        idx_a = sel_a.get("selection", {}).get("rows", [])
        if idx_a:
            ca1, ca2 = st.columns(2)
            if ca1.button(f"🔄 Вернуть на обратно ({len(idx_a)})", key=f"res_btn_{arch_type}"):
                with engine.connect() as conn:
                    for i in idx_a:
                        r = df_arch.iloc[i]
                        conn.execute(text("INSERT INTO stock SELECT uuid, name, article, barcode, quantity, box_num, type FROM archive WHERE uuid=:u"), {"u": r['uuid']})
                        conn.execute(text("DELETE FROM archive WHERE uuid=:u"), {"u": r['uuid']})
                conn.commit()
                reset_selection()
                st.rerun()

            if ca2.button(f"🔥 Очистить ({len(idx_a)})", key=f"clear_btn_{arch_type}"):
                with engine.connect() as conn:
                    for i in idx_a:
                        conn.execute(text("DELETE FROM archive WHERE uuid=:u"), {"u": df_arch.iloc[i]['uuid']})
                conn.commit()
                reset_selection()
                st.rerun()
    else: st.info("Архив пуст")

with t4:
    st.subheader("📋 Текущий расчет (на данный момент)")

    # Считаем то, что лежит в stock прямо сейчас
    df_now = pd.read_sql(text("SELECT * FROM stock"), engine)

    if not df_now.empty:
        b_ip = len(df_now[df_now['type'] == 'ИП'])
        b_ooo = len(df_now[df_now['type'] == 'ООО'])
        
        p_ip = math.ceil(b_ip / 16)
        p_ooo = math.ceil(b_ooo / 16)

        # Создаем две колонки для раздельного отображения
        col_ip, col_ooo = st.columns(2)

        with col_ip:
            st.markdown("### 🏠 ИП")
            st.metric("Коробов (ИП)", b_ip)
            st.metric("Паллет (ИП)", p_ip)
            st.metric("К начислению (ИП)", f"{p_ip * 50} ₽")

        with col_ooo:
            st.markdown("### 🏢 ООО")
            st.metric("Коробов (ООО)", b_ooo)
            st.metric("Паллет (ООО)", p_ooo)
            st.metric("К начислению (ООО)", f"{p_ooo * 50} ₽")

        st.divider()
        # Общий итог внизу
        st.metric("ИТОГО к начислению (Общее)", f"{(p_ip + p_ooo) * 50} ₽")
    else:
        st.write("Склад пуст")

    st.divider()

    st.subheader("📜 История начислений (архив 23:00)")
    try:
        history_df = pd.read_sql(text("SELECT * FROM daily_storage_logs ORDER BY log_date DESC"), engine)
        if not history_df.empty:
            history_df.columns = ["Дата", "Кор. ИП", "Пал. ИП", "₽ ИП", "Кор. ООО", "Пал. ООО", "₽ ООО", "Всего кор.", "Всего пал.", "Итого ₽"]
            st.dataframe(history_df, use_container_width=True, hide_index=True)
        else:
            st.info("История пуста. Первая запись в архиве появится сегодня в 23:00.")
    except Exception:
        st.warning("Таблица истории еще не создана.")

with t5:
    df_all = pd.read_sql(text("SELECT * FROM stock"), engine)
    if not df_all.empty:
        res = df_all.groupby(["type", "barcode"])["quantity"].sum().reset_index()
        res.columns = ["Тип", "Баркод", "Общее количество"]
        st.dataframe(res, use_container_width=True, hide_index=True)














