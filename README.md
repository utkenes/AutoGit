# AutoGit

## Commit güvenliği

AutoGit, her commit öncesinde (watch mode dâhil) repository'nin normal bir
branch üzerinde ve `HEAD`'inin mevcut olduğunu, ayrıca devam eden merge, rebase,
cherry-pick veya revert işlemi bulunmadığını doğrular. Repository güvenli değilse
kalite kontrollerini çalıştırmadan durur.

Kullanıcı önceden dosya stage etmişse AutoGit çalışmaz. Mevcut staging area'yı
asla temizlemez veya değiştirmez; tekrar denemeden önce dosyaları kendiniz
`git restore --staged .` ile unstage edin.

`autogit commit --dry-run`, stage edilecek ve hariç tutulacak dosyaları gösterir.
Önizleme stage işlemi, kalite kontrolü, commit veya başka bir Git değişikliği
yapmaz.

Gerçek committe aday dosyalar önce stage edilir; secret taraması staged Git blob
içeriğini okur. Böylece taranan içerik commitlenen içerikle aynıdır. Tarama,
kalite kontrolü veya mesaj üretimi başarısız olursa AutoGit yalnızca kendi stage
ettiği dosyaları unstage eder. Silinmiş ve binary dosyalar güvenle commit kapsamına
alınır, ancak içerik taramasında atlanır.

AutoGit, seçtiğiniz Git repository’sini izleyen; değişiklikler durulduktan sonra secret taraması ve kalite kontrolleri yapıp güvenli bir yerel commit oluşturan Python CLI aracıdır. Varsayılan olarak push yapmaz.

## Özellikler

- Typer ve Rich ile Türkçe, okunabilir CLI
- Watchdog ile debounce tabanlı dosya izleme
- `.env`, sertifika ve private-key dosyalarını otomatik stage dışında bırakma
- Maskeli secret taraması (OpenAI, Gemini/Google, GitHub, AWS, bearer token, private key ve yaygın parola kalıpları)
- Test, lint ve isteğe bağlı mypy kontrolü
- Local Conventional Commit mesajı üretimi; gelecekte cloud provider eklemeye uygun protocol
- Dönen ve maskeli `.autogit/logs/autogit.log` günlüğü

## Kurulum

Windows PowerShell:

```powershell
cd "D:\laragon\www\staj\laravel v1\git-bot"
python -m pip install -e ".[dev]"
autogit --help
```

Linux/macOS:

```bash
python3 -m pip install -e '.[dev]'
autogit --help
```

Python 3.12 veya üstü gerekir.

## Hızlı başlangıç

```powershell
cd "D:\ornek-proje"
autogit init
autogit doctor
autogit watch
```

İzlemek istediğiniz repository farklıysa `--path` ile doğrudan belirtebilirsiniz:

```powershell
autogit status --path "D:\ornek-proje"
```

## Komutlar

| Komut | Açıklama |
| --- | --- |
| `autogit init` | `.autogit.toml`, runtime klasörü ve gitignore girdilerini hazırlar. |
| `autogit watch` | Değişiklikleri izler ve debounce sonunda commit akışını çalıştırır. |
| `autogit commit` | Tek seferlik güvenli commit akışını başlatır. |
| `autogit status` | Repository, değişiklik ve aktif ayarları gösterir. |
| `autogit config` | Yapılandırmayı JSON olarak gösterir. |
| `autogit config set auto_push false` | Tip güvenli desteklenen bir ayarı günceller. |
| `autogit doctor` | Ortam ve repository sağlığını PASS/WARNING/ERROR olarak raporlar. |

## Yapılandırma

`autogit init` sonrasında `.autogit.toml` oluşturulur. Örnek varsayılanlar:

```toml
debounce_seconds = 60
auto_push = false
run_tests = true
run_lint = true
run_type_check = false
```

`auto_push = true` yalnızca remote mevcutsa push dener. Push hatası commit’i geri almaz; hata açıkça raporlanır.

## Güvenlik yaklaşımı

AutoGit hiçbir zaman `git add .` kullanmaz. Önce Git durumundan aday dosyaları alır, engelli dosya adlarını çıkarır, repository dışı yolları reddeder ve taranabilen dosyalarda secret taraması yapar. Secret bulunursa commit durur; yol, satır, tür ve maskeli değer görünür. Değerin tamamı terminale veya loga yazılmaz. Tehlikeli bypass seçeneği yoktur.

`.env.example` stage edilebilir; ancak gerçek bir anahtar içeriyorsa commit engellenir.

## Otomatik commit akışı

`Dosya olayı → debounce → secret taraması → test/lint/type check → güvenli stage → mesaj → local commit → isteğe bağlı push`

Commit sırasında gelen olaylar pending durumda tutulur; tamamlanan işlemden sonra yeni debounce turu başlar.

## Geliştirme

```bash
python -m ruff check .
python -m mypy autogit
python -m pytest
```

## Mimari

`CLI → application services → domain contracts/models → infrastructure`

- `application`: commit, watcher, kalite, durum ve doctor iş akışları
- `infrastructure`: Git, subprocess, watchdog, secret tarama ve logging
- `domain`: veri modelleri, hata türleri ve provider protocolü
- `providers`: tamamen yerel commit mesajı üretici

## Katkı ve yol haritası

Katkılar için yeni davranışa test ekleyin, Ruff/Mypy/Pytest çalıştırın ve Conventional Commit kullanın. Sonraki sprintte Gemini tabanlı opt-in provider, daha geniş secret detector seti, ince ayarlı config güncellemeleri ve kalite komutları için zaman aşımı eklenebilir.

## Bilinen sınırlamalar

İlk MVP yalnızca local mesaj sağlayıcısını içerir. Secret taraması sezgiseldir ve binary/büyük dosyaları atlar. Watchdog’un işletim sistemi dosya olaylarına bağımlı yapısı nedeniyle çok yüksek frekanslı değişimlerde olaylar birleşebilir; debounce davranışı yine korunur.
