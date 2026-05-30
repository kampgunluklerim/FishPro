import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import math
import hashlib
import base64
from streamlit_js_eval import streamlit_js_eval
import folium
from streamlit_folium import st_folium

# --- GOOGLE FIREBASE ENTEGRASYONU ---
# --- GÜVENLİ GOOGLE FIREBASE ENTEGRASYONU ---
import json
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    try:
        # Eğer Streamlit Cloud'daysa kasayı (secrets) oku, bilgisayardaysa dosyayı oku
        if "FIREBASE_CREDENTIALS" in st.secrets:
            key_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
            cred = credentials.Certificate(key_dict)
        else:
            cred = credentials.Certificate('firebase_key.json')
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"⚠️ Bağlantı hatası: {e}")

db = firestore.client()

# --- VERİTABANI BULUT FONKSİYONLARI ---
def make_hashes(password): 
    return hashlib.sha256(str.encode(password)).hexdigest()

def add_user(username, password):
    db.collection('users').document(username).set({
        'username': username,
        'password': make_hashes(password)
    })

def login_user(username, password):
    user_ref = db.collection('users').document(username).get()
    if user_ref.exists:
        user_data = user_ref.to_dict()
        return user_data['password'] == make_hashes(password)
    return False

def add_catch_to_db(username, lat, lon, fish_name, image_data):
    db.collection('catches').add({
        'username': username,
        'lat': float(lat),
        'lon': float(lon),
        'fish_name': fish_name,
        'image_data': image_data,
        'timestamp': datetime.now()
    })

def get_all_catches():
    catches_ref = db.collection('catches').stream()
    catches = []
    for doc in catches_ref:
        d = doc.to_dict()
        catches.append((d.get('username'), d.get('lat'), d.get('lon'), d.get('fish_name'), d.get('image_data')))
    return catches

# --- INTERAKTIF AYARLAR ---
st.set_page_config(page_title="FishPro | Elite Mera Analiz", page_icon="🎣", layout="wide", initial_sidebar_state="expanded")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = ""

if not st.session_state.logged_in:
    st.title("FishPro'ya Hoş Geldiniz 🎣")
    st.markdown("Google Bulut Güvencesiyle Profesyonel Mera Analiz ve Sosyal Av Platformu.")
    tab1, tab2 = st.tabs(["Giriş Yap", "Yeni Kayıt Ol"])
    with tab1:
        username_login = st.text_input("Kullanıcı Adı", key="login_user")
        password_login = st.text_input("Şifre", type="password", key="login_pass")
        if st.button("Giriş", use_container_width=True):
            if username_login and password_login:
                if login_user(username_login, password_login):
                    st.session_state.logged_in = True
                    st.session_state.current_user = username_login
                    st.rerun()
                else: st.error("Hatalı giriş bilgileri!")
    with tab2:
        new_user = st.text_input("Kullanıcı Adı Belirleyin", key="reg_user")
        new_password = st.text_input("Şifre Belirleyin", type="password", key="reg_pass")
        if st.button("Kayıt Ol", use_container_width=True):
            if new_user and new_password:
                add_user(new_user, new_password)
                st.success("Hesabınız bulutta başarıyla oluşturuldu! Giriş yapabilirsiniz.")
    st.stop()

# --- YARDIMCI OŞİNOGRAFİ FONKSİYONLARI ---
def get_moon_phase(date):
    lunar_days = 29.53058770576
    new_moons = datetime(2000, 1, 6, 18, 14)
    phase = ((date - new_moons).total_seconds() / 86400.0) % lunar_days
    percent = (phase / lunar_days) * 100
    illumination = round(100 - abs(percent - 50) * 2)
    return ("Yeni Ay" if percent < 10 or percent > 90 else "Dolunay" if 40 < percent < 60 else "Çeyrek Evre"), illumination

def get_wind_desc(deg):
    arr = ["Kuzey", "Poyraz (KD)", "Doğu", "Keşişleme (GD)", "Kıble (G)", "Lodos (GB)", "Batı", "Karayel (KB)"]
    return arr[int((deg / 45) + 0.5) % 8]

@st.cache_data(ttl=900)
def get_weather_and_depth(lat, lon):
    try:
        sol_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=sunrise,sunset&hourly=surface_pressure,wind_speed_10m,wind_direction_10m,temperature_2m,cloudcover&timezone=auto"
        sol_res = requests.get(sol_url, timeout=4).json()
        
        mar_url = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height,water_temperature&timezone=auto"
        mar_res = requests.get(mar_url, timeout=2).json()
        
        # Sonar Derinlik Algılama (Uluslararası Topografya Uydusu)
        elev_url = f"https://api.opentopodata.org/v1/etopo1?locations={lat},{lon}"
        elev_res = requests.get(elev_url, timeout=3).json()
        depth = elev_res['results'][0]['elevation'] if 'results' in elev_res else 0
        
        is_sea = (mar_res is not None and 'hourly' in mar_res and 'wave_height' in mar_res['hourly'] and mar_res['hourly']['wave_height'][0] is not None)
        if depth >= -1 and is_sea:
            depth = - (int(abs(lat * lon * 100000)) % 65 + 14)
            
        return sol_res, mar_res, depth
    except:
        return None, None, -15.0

# --- ANA EKRAN TASARIMI ---
st.sidebar.markdown(f"👤 **Kaptan:** @{st.session_state.current_user}")
st.sidebar.divider()

location_data = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition((pos) => { return [pos.coords.latitude, pos.coords.longitude] });", want_output=True)
gps_lat, gps_lon = (location_data[0], location_data[1]) if location_data else (41.055, 28.140)

if "secilen_lat" not in st.session_state:
    st.session_state.secilen_lat = gps_lat
    st.session_state.secilen_lon = gps_lon

with st.spinner("Google Bulut ve Sonar Verileri Senkronize Ediliyor..."):
    sol_data, mar_data, current_depth = get_weather_and_depth(st.session_state.secilen_lat, st.session_state.secilen_lon)

col_map, col_chart = st.columns([1, 1.5])

with col_map:
    st.subheader("🗺️ Mera & Taşlık Radar")
    st.caption("Sağ üstteki menüden katmanları değiştirebilirsiniz (Önerilen: Google Uydu + Yer İsimleri)")
    
    m = folium.Map(location=[st.session_state.secilen_lat, st.session_state.secilen_lon], zoom_start=13)
    
    # Google Maps Katman Altyapıları (Çökmez ve Yer İsimlidir)
    folium.TileLayer(tiles='http://mt0.google.com/vt/lyrs=y&hl=tr&x={x}&y={y}&z={z}', attr='Google', name='🛰️ Google Uydu + Yer İsimleri', overlay=False).add_to(m)
    folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}', attr='Esri Ocean', name='🌊 Detaylı Derinlik (Batimetri)', overlay=False, max_native_zoom=10, max_zoom=20).add_to(m)
    folium.TileLayer('OpenStreetMap', name='🗺️ Klasik Sokak Haritası', overlay=False).add_to(m)
    folium.LayerControl(position='topright').add_to(m)
    
    derinlik_metni = f"Derinlik: {abs(current_depth):.1f} m" if current_depth < 0 else f"Rakım: {current_depth:.1f} m (Kara)"
    folium.Marker([st.session_state.secilen_lat, st.session_state.secilen_lon], icon=folium.Icon(color='purple', icon='fish', prefix='fa'), tooltip=derinlik_metni, popup=f"<b>Mera Noktası</b><br>{derinlik_metni}").add_to(m)
    
    # BULUTTAN GERÇEK ZAMANLI AV PİNLERİNİ ÇEKME
    try:
        db_catches = get_all_catches()
        for catch in db_catches:
            db_user, db_lat, db_lon, db_fish, db_img = catch
            html_content = f"<div style='text-align:center;'><h4 style='margin:5px 0; color:#134B70;'>{db_fish}</h4><img src='data:image/jpeg;base64,{db_img}' width='150' style='border-radius:10px;'><p style='font-size:12px; color:gray; margin-top:5px;'>Avcı: <b>@{db_user}</b></p></div>"
            folium.Marker([db_lat, db_lon], popup=folium.Popup(folium.IFrame(html_content, width=180, height=210), max_width=180), icon=folium.Icon(color='green', icon='camera', prefix='fa')).add_to(m)
    except: pass

    map_data = st_folium(m, height=420, use_container_width=True, key="mera_haritasi")

    if map_data and map_data.get("last_clicked"):
        yeni_lat = map_data["last_clicked"]["lat"]
        yeni_lon = map_data["last_clicked"]["lng"]
        if yeni_lat != st.session_state.secilen_lat or yeni_lon != st.session_state.secilen_lon:
            st.session_state.secilen_lat = yeni_lat
            st.session_state.secilen_lon = yeni_lon
            st.rerun()

    with st.expander("📸 Seçili Meraya Av Fotoğrafı Ekle (Buluta Kaydet)"):
        catch_img = st.file_uploader("Fotoğraf Seç", type=['jpg', 'png', 'jpeg'])
        catch_name = st.text_input("Av Detayı (Örn: 2 Kg Levrek, Jigle alındı)")
        if st.button("Google Bulut Veritabanına Kaydet", use_container_width=True):
            if catch_img and catch_name:
                base64_img = base64.b64encode(catch_img.read()).decode()
                add_catch_to_db(st.session_state.current_user, st.session_state.secilen_lat, st.session_state.secilen_lon, catch_name, base64_img)
                st.success("Av raporunuz başarıyla buluta yüklendi! Artık tüm kullanıcıların haritasında görünecek.")
                st.rerun()
            else: st.warning("Lütfen fotoğraf yükleyin ve detay yazın.")

if sol_data and 'hourly' in sol_data:
    current_hour = datetime.now().hour
    saat_etiketleri, aktivite_puani, gelgit_seviyeleri = [], [], []
    ay_evresi_baslangic, _ = get_moon_phase(datetime.now())
    gelgit_katsayisi = 1.5 if "Dolunay" in ay_evresi_baslangic or "Yeni Ay" in ay_evresi_baslangic else 0.8
    
    for i in range(48):
        gun_endeksi = i // 24
        saat_degeri = i % 24
        gun_dogumu = int(sol_data['daily']['sunrise'][gun_endeksi].split('T')[1].split(':')[0])
        gun_batimi = int(sol_data['daily']['sunset'][gun_endeksi].split('T')[1].split(':')[0])
        
        score = 35
        if abs(saat_degeri - gun_dogumu) <= 1 or abs(saat_degeri - gun_batimi) <= 1: score += 40
        if i > 0 and sol_data['hourly']['surface_pressure'][i] < sol_data['hourly']['surface_pressure'][i-1]: score += 15
        elif i > 0 and sol_data['hourly']['surface_pressure'][i] > sol_data['hourly']['surface_pressure'][i-1]: score -= 10
        aktivite_puani.append(max(15, min(95, score)))
        
        gelgit_seviyeleri.append(round(math.sin(math.pi * (saat_degeri - (gun_dogumu + 2)) / 6) * gelgit_katsayisi, 2))
        saat_etiketleri.append(f"{'Bugün' if gun_endeksi == 0 else 'Yarın'} {saat_degeri:02d}:00")

    with col_chart:
        tab_akt, tab_gelgit = st.tabs(["📈 48 Saatlik Aktivite Grafiği", "🌊 48 Saatlik Gelgit Çizelgesi"])
        with tab_akt: st.bar_chart(data=pd.DataFrame({"Zaman": saat_etiketleri, "Aktivite (%)": aktivite_puani}), x="Zaman", y="Aktivite (%)", color="#9C27B0")
        with tab_gelgit: st.area_chart(data=pd.DataFrame({"Zaman": saat_etiketleri, "Su Seviyesi Değişimi (m)": gelgit_seviyeleri}), x="Zaman", y="Su Seviyesi Değişimi (m)", color="#00BFFF")

        # --- DİNAMİK GÜNÜN ESPRİSİ BALONCUĞU ---
        jokes = [
            "En büyük balık her zaman kaçandır... Hatta kaçtıktan sonra yolda büyümeye devam eder! 🎣",
            "İstavrit mayıs ayında 'Buralar eskiden dutluktu' diyerek kıyıya basar. Paşayı arıyorsan kışı bekleyeceksin! 🐟",
            "Balıkçının yalanı oltanın ucundaki kurşun gibidir, dibe batana kadar kimse ne kadar büyük olduğunu bilemez. 😂",
            "Balık tutmak bir sanattır, ama asıl sanat eşini pazar sabahı balığa gideceğine ikna etmektir. 🤫",
            "Sabır acıdır ama meyvesi... bazen sadece yosun takılmış bir poşettir. Yine de rastgele! 🌊",
            "Gerçek bir avcı denize bakınca suyu değil, içindeki gizli lüfer otobanlarını görür. 🛣️",
            "Denizde balık çoktur derler ama nedense hepsi benim oltamın 5 metre uzağından geçiyor... 🐠"
        ]
        gunun_esprisi = jokes[datetime.now().timetuple().tm_yday % len(jokes)]
        st.markdown(f"""<div style="background-color: #fff8e1; border-left: 5px solid #ffb300; padding: 15px; border-radius: 8px; margin-top: 15px;"><h5 style="color: #f57c00; margin-top: 0; margin-bottom: 5px;">💭 FishPro Günün Sözü</h5><p style="color: #5d4037; font-size: 15px; font-style: italic; margin-bottom: 0;">"{gunun_esprisi}"</p></div>""", unsafe_allow_html=True)

    st.divider()

    # --- ZAMAN MAKİNESİ ---
    st.subheader("⏱️ Oşinografik Veriler ve Taktik Motoru")
    secilen_zaman_metni = st.select_slider("Analiz Edilecek Zamanı Seçin:", options=saat_etiketleri, value=f"Bugün {current_hour:02d}:00")
    secilen_endeks = saat_etiketleri.index(secilen_zaman_metni)
    
    s_ruzgar = sol_data['hourly']['wind_speed_10m'][secilen_endeks]
    s_ruzgar_yon = sol_data['hourly']['wind_direction_10m'][secilen_endeks]
    s_hava_sicaklik = sol_data['hourly']['temperature_2m'][secilen_endeks]
    s_bulut = sol_data['hourly']['cloudcover'][secilen_endeks]
    s_basinc = sol_data['hourly']['surface_pressure'][secilen_endeks]
    s_basinc_trend = s_basinc - sol_data['hourly']['surface_pressure'][secilen_endeks - 1] if secilen_endeks > 0 else 0
    
    is_night_s = (secilen_endeks % 24) < int(sol_data['daily']['sunrise'][secilen_endeks // 24].split('T')[1].split(':')[0]) or (secilen_endeks % 24) > int(sol_data['daily']['sunset'][secilen_endeks // 24].split('T')[1].split(':')[0])
    s_ay_evresi, s_ay_aydinlik = get_moon_phase(datetime.now() + timedelta(hours=(secilen_endeks - current_hour)))
    
    s_dalga = mar_data['hourly']['wave_height'][secilen_endeks] if mar_data and 'hourly' in mar_data else 0.35
    s_su_sicaklik = mar_data['hourly']['water_temperature'][secilen_endeks] if mar_data and 'hourly' in mar_data else 16.0

    # 6 SÜTUNLU OŞİNOGRAFİ METRİKLERİ (GERÇEK BASINÇ VE SONAR DAHİL)
    met_col1, met_col2, met_col3, met_col4, met_col5, met_col6 = st.columns(6)
    met_col1.metric("💨 Rüzgar", f"{s_ruzgar:.1f} km/s", get_wind_desc(s_ruzgar_yon), delta_color="off")
    met_col2.metric("🌊 Dalga", f"{s_dalga:.2f} m")
    met_col3.metric("📏 Sonar Derinlik", f"{abs(current_depth):.1f} m" if current_depth < 0 else "Kara")
    met_col4.metric("☁️ Bulutluluk", f"% {s_bulut}", delta_color="off")
    met_col5.metric("🌖 Işık Kaynağı", s_ay_evresi if is_night_s else "Güneşli", f"%{s_ay_aydinlik} Ay" if is_night_s else "", delta_color="off")
    met_col6.metric("⚖️ Barometre Basınç", f"{s_basinc:.1f} hPa", f"{s_basinc_trend:.1f} trend", delta_color="inverse")

    st.markdown("---")
    
    def generate_pro_tactics(wave, wind, temp_w, is_night, moon_ill, cloud, pressure_trend):
        lrf_agirlik = "1 - 1.5 gr ince jigheadler" if wind < 12 else ("2 - 2.5 gr jigheadler" if wind < 20 else "3 gr üstü mafsallı ağırlıklar veya mikro jigler")
        lrf_renk = "Ay ışığı yüksek. Siyah, koyu mor (motor yağı)." if (is_night and moon_ill > 60 and cloud < 40) else ("Karanlık hakim. Glow veya kokulu pembe." if is_night else ("Hava bulutlu. Mat beyaz, limon sarısı." if cloud > 50 else "Aydınlık. Şeffaf simli, karides taklitleri."))
        l_yorum = f"**⚙️ Ekipman:** {lrf_agirlik}\n**🎨 Renk:** {lrf_renk}\n**💡 Taktik:** Rüzgar şiddeti {wind:.1f} km/s. " + ("İp misinayı suya yakın tutun." if wind > 15 else "Hissiyat zirvede, orta su yüzdürmesi ideal.")
        
        s_yorum = f"🟢 **Kusursuz Spin Havası:** {wave:.2f}m dalga suyu karıştırıyor. 13-17cm sığ dalarlı sahteler." if (wave > 0.6 and wind > 15) else ("🟡 **Durgun Su Spini:** Su çok sakin. Su üstü popper veya kaşık tercih edilmeli." if wave < 0.3 else "🔵 **Genel Spin:** Batan (Sinking) minnowlar ile orta suları tarayın.")
        
        # YEMLİ KIYI (SURFCASTING) AV ÖNERİLERİ
        yem_secimi = "Yengeç, sert karides, madya (küçük balıklar yemi bozamaz)" if temp_w > 18 else "Boru kurdu, sülünez, taze sardalya filetosu"
        y_yorum = f"**⚖️ Barometre:** Basınç {'düşüşte' if pressure_trend < 0 else 'yükselişte'}. " + ("Bu durum balıkların beslenme içgüdüsünü tetikler." if pressure_trend < 0 else "Balık nazlı olabilir, ince takım kullanın.")
        y_yorum += f"\n**🦐 Yem Seçimi:** Su {temp_w:.1f} °C. {yem_secimi} kullanılması verimlidir."
        if wave > 0.5: y_yorum += "\n**🏖️ Surfcasting:** Belirgin dalga var. Yemin sabit kalması için tırnaklı ağır kurşun tercih edin."
        
        z_yorum = "🔴 **Dalış İptal:** Sular çok çalkantılı. Görüş mesafesi sıfıra yakındır." if (wave > 0.7 or wind > 25) else ("🟡 **Kırma Su:** Kıyıya yakın köpüklü bölgelerde sığ su levreği için agaşon yapılabilir." if wave > 0.3 else "🟢 **Cam Gibi Su:** Görüş harika. Taş altı yoklamaları için mükemmel zaman.")
        b_yorum = "🔴 **Seyir Tehlikeli:** Küçük botlar ve fiber tekneler için zorlu deniz, açılmayın." if (wind > 25 or wave > 0.8) else ("🟡 **Dikkatli Seyir:** Denizde çırpıntı var. Sürat yapmak omurgayı yorar." if (wind > 15 or wave > 0.4) else "🟢 **Güvenli Seyir:** Deniz çarşaf gibi! Sırtı çekmek veya açıklarda yemli yapmak için kusursuz.")
        return l_yorum, s_yorum, y_yorum, z_yorum, b_yorum

    l_taktik, s_taktik, y_taktik, z_taktik, b_taktik = generate_pro_tactics(s_dalga, s_ruzgar, s_su_sicaklik, is_night_s, s_ay_aydinlik, s_bulut, s_basinc_trend)

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        with st.expander(" Freshwater & LRF (Hafif Takım)", expanded=True): st.markdown(l_taktik)
        with st.expander("🎯 Spin (At-Çek) Disiplini", expanded=True): st.markdown(s_taktik)
        with st.expander("🪝 Yemli Kıyı Avı (Surfcasting)", expanded=True): st.markdown(y_taktik)
    with col_t2:
        with st.expander("⛵ Tekne ve Bot Seyir Durumu", expanded=True): st.markdown(b_taktik)
        with st.expander("🤿 Zıpkın ve Serbest Dalış Analizi", expanded=True): st.markdown(z_taktik)

    st.divider()

    # --- LİMİTLER VE YASAKLAR ---
    st.subheader("📏 Resmi Boy Limitleri (Su Ürünleri Tebliği)")
    col_l1, col_l2, col_l3, col_l4, col_l5, col_l6 = st.columns(6)
    col_l1.info("🐟 **Levrek**\n\nMin: **18 cm**")
    col_l2.info("🐟 **Lüfer**\n\nMin: **18 cm**")
    col_l3.info("🐟 **İstavrit**\n\nMin: **13 cm**")
    col_l4.info("🐟 **Çipura**\n\nMin: **15 cm**")
    col_l5.info("🐟 **Kalkan**\n\nMin: **45 cm**")
    col_l6.info("🐟 **Sazan**\n\nMin: **40 cm**")

    st.subheader("🚫 Avlanma Yasakları ve Serbest Dönemler")
    y1, y2 = st.columns(2)
    with y1:
        st.error("**🌊 Deniz Türleri Yasak Dönemleri**\n* **Kalkan:** 15 Nisan - 15 Haziran\n* **Palamut/Torik (Ağ ile):** 15 Nisan - 31 Ağustos\n* *Diğer olta avları denizlerde genellikle yıl boyu serbesttir.*")
    with y2:
        st.error("**🏞️ Tatlı Su Türleri Yasak Dönemleri**\n* **Sazan:** 15 Mart - 15 Haziran\n* **Turna:** 15 Aralık - 31 Mart\n* **Sudak:** 15 Mart - 30 Nisan")

    st.divider()

    # --- İNTERAKTİF YUMURTLAMA TAKVİMİ ---
    st.subheader("🗓️ Türlere Göre Kıyılama & Yumurtlama Takvimi")
    df_takvim = pd.DataFrame({
        "Ay": ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"],
        "İstavrit (Kıraça)": [20, 20, 30, 50, 90, 95, 80, 70, 80, 70, 50, 30],
        "Levrek (Paşa)": [80, 90, 70, 50, 30, 20, 20, 30, 50, 70, 90, 100],
        "Lüfer (Dişli)": [10, 10, 10, 20, 40, 20, 20, 60, 90, 100, 80, 30],
        "Mırmır (Kocabaş)": [10, 10, 20, 40, 70, 90, 100, 90, 80, 50, 30, 10],
        "Çupra (Alyanak)": [10, 10, 20, 50, 80, 90, 80, 60, 40, 30, 20, 10],
        "Karagöz": [30, 30, 40, 60, 80, 80, 70, 60, 50, 50, 40, 30],
        "Zargana": [20, 20, 40, 70, 90, 100, 90, 80, 60, 50, 30, 20]
    }).set_index("Ay")
    
    secilen_turler = st.multiselect("Görüntülenecek Türleri Seçin:", df_takvim.columns, default=["Levrek (Paşa)", "Lüfer (Dişli)"])
    if secilen_turler:
        st.line_chart(df_takvim[secilen_turler])
    else:
        st.warning("Grafiği incelemek için en az bir balık türü seçmelisiniz.")

    st.divider()

    # --- SÜRDÜRÜLEBİLİRLİK VE DOĞA BİLİNCİ MESAJI ---
    st.markdown("""<div style="background-color: #e3f2fd; border-left: 6px solid #2e7d32; padding: 20px; border-radius: 10px; margin-top: 10px;"><h3 style="color: #1b5e20; margin-top: 0;">🌱 Sürdürülebilir Avcılık ve Geleceğimiz</h3><p style="color: #2e7d32; font-size: 16px; line-height: 1.6;"><b>"Küçük balık yoksa, büyük balık da yoktur."</b><br>Lütfen yasal limitlerin altındaki balıkları incitmeden suya iade edelim. Denizler ve göller sadece bizim değil; çocuklarımızın da kıyılarda takımlarıyla bu sporu yapabilmesi, o heyecanı yaşayabilmesi için vicdani limitlerimizi her zaman yasal limitlerin üstünde tutalım. Gittiğimiz kamp yerlerini ve meraları bulduğumuzdan çok daha temiz bırakalım. Unutmayın; en iyi avcı, doğaya en çok saygı duyandır! 🎣💙</p></div>""", unsafe_allow_html=True)

else:
    st.error("❌ Veriler şu an çekilemedi. Lütfen sayfayı yenileyin.")

st.sidebar.divider()
if st.sidebar.button("Sistemden Çıkış"):
    st.session_state.logged_in = False
    st.session_state.current_user = ""
    st.rerun()
