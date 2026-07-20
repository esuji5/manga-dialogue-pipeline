# manga-dialogue-pipeline

自分で用意したマンガ画像から、セリフ・コマ・人物boxの座標を構造化JSONへ取り出し、話者を付け、ローカル検索画面を起動するためのスクリプト集です。

このリポジトリに画像、抽出済みセリフ、人物名簿、gold、APIレスポンスは含まれません。入力画像とGemini APIキーは利用者が用意してください。

本書で作った検索システムの公開版は、[yuyusearch.subcatalog.net](https://yuyusearch.subcatalog.net/)で動かしています。実作品については、検索結果の巻・頁・コマ番号だけを返し、セリフ本文・話者名・画像は返しません。

## できること

```text
ページ画像
  → コマ・人物box・セリフ・読み順を抽出
  → 任意: 非マンガページを分類して除外
  → 任意: セリフを人物boxと人物名へ接続
  → SQLite FTS5へ登録
  → CLIまたはWeb画面で検索
```

- 3文字以上はSQLite FTS5 trigram、1〜2文字は`LIKE`で部分一致
- work、ページ、コマ、話者による絞り込み
- `unknown`話者の除外
- 該当コマのローカル画像表示
- 公開用に本文と画像をAPI段階で隠すモード

現在のVLM接続はGeminiです。モデルIDは固定せず、`.env`または`--model`で指定します。
API呼び出しは既定で5分のtimeoutと最大3回の試行を設定しています。必要なら
`GEMINI_TIMEOUT_MS`と`GEMINI_RETRY_ATTEMPTS`で変更できます。

## セットアップ

Python 3.11以上と[uv](https://docs.astral.sh/uv/)を使います。

```bash
git clone git@github.com:esuji5/manga-dialogue-pipeline.git
cd manga-dialogue-pipeline

cp .env.example .env
# .env に GOOGLE_API_KEY と、利用できる GEMINI_MODEL を設定

uv sync --extra dev
```

`images/`へ、自分が処理する権利を持つページ画像を置きます。画像と生成物は`.gitignore`の対象です。

## 最短で動かす

セリフ全文検索まで:

```bash
uv run python scripts/run_pipeline.py ./images \
  --work-id mybook \
  --route \
  --serve
```

抽出と索引作成後、`http://127.0.0.1:8787`が開けます。人物名簿がないため、話者は`unknown`のままです。

話者検索まで:

```bash
cp config.example.yaml characters.yaml
# characters.yamlを自分の作品の人物名簿に書き換える

uv run python scripts/run_pipeline.py ./images \
  --work-id mybook \
  --route \
  --link-speakers \
  --characters characters.yaml \
  --serve
```

人物名簿を渡さないまま`--link-speakers`を使うこともできます。その場合、吹き出しと人物boxの対応は作りますが、人物名は`null`になります。

## 工程を個別に実行する

### 1. ページを構造化する

```bash
uv run python scripts/extract_pages.py ./images \
  --work-id mybook \
  --route
```

出力は`data/mybook/pages/*.json`です。元のセリフ本文には話者名を混ぜません。

### 2. 話者を付ける

```bash
uv run python scripts/link_speakers.py \
  --work-id mybook \
  --characters characters.yaml
```

出力は`data/mybook/speakers/*.json`です。抽出JSONは書き換えません。

### 3. 検索DBを作る

```bash
uv run python scripts/build_search_index.py \
  --data-dir data \
  --out data/search.db
```

構造化JSONを再取得せず、検索DBだけ何度でも作り直せます。

### 4. 検索する

```bash
uv run python scripts/search.py "覚えているセリフ"
uv run python scripts/search.py --speaker "人物名" --work mybook
uv run python scripts/search.py "短い語" --exclude-unknown

uv run python scripts/serve.py
```

## 公開モード

検索サーバーを外部から触れる場所へ置く場合、実作品の本文や画像を返さないモードがあります。

```bash
uv run python scripts/serve.py --host 0.0.0.0 --public
```

公開モードでは検索自体は行いますが、結果は`work_id`、ページ、コマ番号だけです。本文、話者名、画像URL、bboxはAPIレスポンスに含めません。

自作サンプルなど、配布可能なworkだけ内容を表示する場合:

```bash
uv run python scripts/serve.py \
  --host 0.0.0.0 \
  --public \
  --full-content-work my-original-work
```

ローカルモードのまま`0.0.0.0`へbindすることはできません。

## プロンプト

- [`prompts/page_router.md`](prompts/page_router.md): マンガページかどうかの分類
- [`prompts/page_extraction.md`](prompts/page_extraction.md): セリフ・コマ・人物box・座標の抽出
- [`prompts/speaker_linking.md`](prompts/speaker_linking.md): セリフと人物box・人物名の接続

出力スキーマはPydanticで固定しています。詳細は[`docs/data-format.md`](docs/data-format.md)を参照してください。

## テスト

テストは偽のVLM応答と架空のセリフだけを使い、外部APIを呼びません。

```bash
uv run pytest
uv run ruff check .
```

確認対象:

- 画像→抽出JSON→話者JSON→検索DBの接続
- 話者工程を省略した全文検索
- 短い語とFTS5検索
- 公開APIから本文・画像情報が消えること
- 許可した自作workだけ内容を表示できること

## 注意

- LLMの出力は正解ではありません。話者名、読み順、bboxは誤ることがあります。
- API利用料はモデル、画像サイズ、ページ数によって変わります。
- 画像を外部APIへ送信する前に、利用条件と権利を確認してください。
- `.env`、`images/`、`data/`はコミットしないでください。

## License

MIT
