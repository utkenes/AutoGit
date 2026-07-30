# AutoGit

AutoGit, değişiklikleri analiz eden, mantıksal commit planı sunan ve kullanıcı
onayı olmadan hiçbir commit veya push yapmayan kontrollü bir Git asistanıdır.

## Hızlı başlangıç

```powershell
cd "D:\ornek-proje"
autogit start
```

`start` repository'yi ve güvenlik durumunu denetler. İlk çalıştırmada gerekli
olursa Git repository/config kurulumu ve isteğe bağlı test-lint tespiti için
yönlendirme yapar. Ardından önerilen commit gruplarını gösterir:

```text
[A] Onayla
[E] Mesajları düzenle
[C] İptal
```

Onaydan sonra kalite ve secret kontrolleri çalışır. Başarılı gruplar sırayla
local commit olur; push için en sonda ayrıca onay istenir.

## Güvenlik

- Önceden stage edilmiş dosyalar varsa işlem durur ve staging area değişmez.
- Merge, rebase, cherry-pick, revert, detached HEAD ve Git `index.lock`
  durumlarında commit yapılmaz.
- Aynı repository için yalnızca bir AutoGit akışı `.autogit/autogit.lock` ile
  yürür. Git'in kendi lock dosyaları asla silinmez.
- Secret taraması stage edilmiş blob içeriğinde yapılır. Hata halinde yalnızca
  AutoGit'in stage ettiği dosyalar geri alınır.
- `.git` ve `.autogit` içeriği commit adayı veya watcher girdisi değildir.

## Komutlar

| Komut | Açıklama |
| --- | --- |
| `autogit start` | Önerilen ana, onaylı planlama ve commit akışı. |
| `autogit status` | Repository ve yapılandırma özetini gösterir. |
| `autogit doctor` | Ortam ve repository sağlığını denetler. |
| `autogit config` | Geçerli yapılandırmayı gösterir/değiştirir. |
| `autogit commit` | Eski tek-commit akışını korur; `--dry-run` destekler. |
| `autogit watch` | Eski watcher komutudur; ana kullanım akışının parçası değildir. |

## Varsayılanlar

İlk kurulumda `run_tests`, `run_lint` ve `auto_push` kapalıdır. AutoGit Python,
JavaScript ve lint altyapısını algıladığında bunları etkinleştirmek için onay
ister. Test veya lint altyapısı yoksa komut çalıştırılmaz.

## Geliştirme

```bash
python -m pytest -q
python -m pytest --cov=autogit --cov-report=term-missing
python -m ruff check .
python -m mypy .
```

## Bilinen sınırlar

Commit planlayıcı ilk sürümde deterministik kurallar kullanır; belirsiz source
değişikliklerinde güvenli, küçük bir grup tercih eder. GitHub API üzerinden
remote repository oluşturma ve AI tabanlı gruplama henüz eklenmemiştir.
