# Fire Safety Monitoring — Dashboard Desktop

Dashboard pemantauan gas, suhu, kelembapan, RFID, dan panduan evakuasi berbasis **Python + Tkinter + MQTT**.

## Antarmuka modern

- Tema biru terinspirasi aplikasi Weather pada gambar referensi: header gradasi, kartu membulat dua kolom, teks putih, dan nilai sensor berukuran besar.
- Suhu ruangan dari DHT22 ditampilkan besar di bagian atas Ringkasan. Tidak menampilkan data cuaca Surabaya, UV, atau angin karena perangkat aplikasi ini tidak menyediakan data tersebut.
- Navigasi horizontal di atas konten; fitur aplikasi Fire Safety tetap tersedia.
- Status sistem ringkas; kartu gas, suhu, dan kelembapan dengan satuan terpisah.
- Indikator waktu pembaruan dan data kedaluwarsa.
- Panel UID RFID serta waktu pemindaian terakhir.
- Navigasi fungsional: Ringkasan, Sensor, Riwayat aktivitas, Evakuasi, Konfigurasi, dan Tentang.
- Konten dapat digulir; kontrol operator dan indikator status sistem tetap terlihat di bawah, termasuk saat berpindah halaman.
- Log ringkasan 60 catatan terakhir; riwayat hingga 300 catatan per sesi.
- Tidak memerlukan paket UI tambahan.

## Menjalankan di Windows

Gunakan interpreter Python yang dipilih pada VS Code, dengan dukungan Tcl/Tk, lalu jalankan pada folder proyek:

Cara praktis tanpa Administrator: klik dua kali **`buka-dashboard.cmd`**. Launcher memakai Python portable yang sudah ada, memeriksa MQTT lokal dan menjalankan Mosquitto biasa bila belum berjalan, lalu membuka `app_v2.py` yang sama. Tidak mengubah service/firewall atau mengirim perintah perangkat. Broker mode pengguna ini tidak dijamin aktif setelah restart Windows; buka lagi launcher. Jangan menjalankan banyak dashboard sekaligus.

```powershell
cd E:\VScode\fire_safety\fire_safety_dashboard
python -m pip install -r requirements.txt
python app_v2.py
```

Jalankan Mosquitto secara terpisah untuk menerima data MQTT. Opsional: `python publisher_test.py` mengirim data simulasi ke broker; jangan gunakan pada sistem operasional tanpa memastikan perangkat yang terhubung aman.

Jika `python` membuka Microsoft Store, pilih interpreter Python yang benar di VS Code dan buka terminal baru, atau gunakan path lengkap ke `python.exe`. Akun SSH dan akun Windows utama dapat mempunyai PATH serta izin berbeda.

Tanpa broker, aplikasi menampilkan **MQTT OFFLINE** dan tetap mencoba menyambung ulang dengan jeda 1–10 detik. Saat broker tersedia kembali, dashboard berlangganan ulang ke topik sensor tanpa perlu ditutup. Nilai sensor kedaluwarsa tetap ditampilkan `--`.

## Struktur proyek

```text
app_v2.py                  Entry point, state, MQTT, dan aksi operator
modern_ui.py               Tata letak dan widget presentasi Tkinter
ui_model.py                Format nilai dan kesegaran sensor
publisher_test.py          Publisher simulasi (tidak diubah)
requirements.txt           Dependensi runtime (tidak diubah)
README.md                  Panduan penggunaan
test_dashboard.py          Tes GUI dan regresi tanpa koneksi broker
test_ui_model.py           Tes format nilai dan kesegaran
test_layout_integration.py Tes integrasi lapisan antarmuka
test_review_regressions.py Tes indikator tetap terlihat dan rute ilustrasi
test_weather_style.py      Tes tema biru, susunan kartu, dan suhu utama tanpa data buatan
```

## Konfigurasi tetap di app_v2.py

- Broker: `127.0.0.1:1883`.
- Gas: `sensor/gas`, payload `{"nilai": 820}` (ppm).
- Suhu/kelembapan: `sensor/suhu`, payload `{"suhu": 28.4, "humidity": 62.7}`.
- RFID: `sistem/rfid`, payload `{"rfid": "3A:5F:9C:21"}`.
- Perintah alarm: `sistem/alarm`.
- Batas gas: **2500 ppm**; batas suhu: **40 °C**.
- Data kedaluwarsa setelah **15 detik**.

Halaman Konfigurasi bersifat **baca-saja**. Pembaruan UI tidak mengubah broker, topik, ambang, payload, atau implementasi publish/subscribe.

## Kontrol operator

- **Bunyikan alarm**: mengirim `{"status": "BAHAYA", "action": "ALARM"}` ke `sistem/alarm`.
- **Reset aman**: mengirim `{"status": "AMAN", "action": "RESET"}` ke `sistem/alarm`.
- **Reset dashboard**: meminta konfirmasi, mengosongkan data sensor/RFID, antrean, status lokal, dan log; **tidak mengirim perintah MQTT**.

Status ringkasan mengikuti evaluasi sensor aplikasi lama. Reset aman tidak menghilangkan bahaya bila sensor masih melewati batas. Status visual dan evaluasi sensor bukan latch alarm fisik; tampilan bukan konfirmasi bahwa aktuator benar-benar aktif atau berhenti.

## Pengujian

```powershell
python -m unittest test_ui_model test_layout_integration test_dashboard test_review_regressions test_weather_style -v
```

Tes GUI memerlukan desktop/Tk yang dapat diakses. Windows SSH berjalan di sesi layanan, bukan desktop pengguna. Tes tidak memulai thread MQTT; pengiriman alarm dimock agar tidak memicu perangkat fisik.

## Keamanan dan batasan

- Diagram adalah **ilustrasi**, bukan peta bangunan terverifikasi atau posisi kebakaran langsung.
- Sensor kosong/kedaluwarsa tidak diganti dengan data buatan.
- Log hanya di memori, tidak bertahan setelah aplikasi ditutup.
- MQTT contoh tanpa autentikasi, hanya untuk jaringan internal/pengujian yang sesuai.
- Ini prototipe/alat bantu visual, **bukan pengganti alarm kebakaran tersertifikasi**. Sistem nyata tetap membutuhkan sensor, aktuator, catu daya, serta prosedur keselamatan yang sesuai.

Proyek dapat digunakan untuk pendidikan/prototyping.
