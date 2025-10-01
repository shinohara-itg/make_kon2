import streamlit as st
import os
import re
from openai import AzureOpenAI
from dotenv import load_dotenv
from datetime import datetime
import yaml
import pandas as pd
from io import BytesIO

# =========================
# 前処理関数（ログ付き）
# =========================
def sanitize_input(text: str, mask_url: bool = True, pii_mode: str = "mask"):
    """
    入力テキストを前処理して返す。
    - 個人情報らしきフィールドをマスクor削除（pii_mode: "mask" | "remove"）
    - URLを [URL] にマスク（mask_url=True）
    - 空欄行や「：の後が空／'様'だけ」の行を削除
    返り値:
      cleaned_text: str
      logs: list[dict]  # 各変更・削除のログ
    """
    lines = text.splitlines()
    cleaned_lines = []
    logs = []

    # 個人情報フィールド（必要に応じて追加）
    sensitive_fields = [
        "氏名", "フリガナ", "メールアドレス", "電話番号",
        "携帯番号", "郵便番号", "住所"
    ]

    # 「キー：値」抽出用（全角/半角コロン対応）
    kv_pattern = re.compile(r"^(?P<key>[^：:]+)[：:]\s*(?P<val>.*)$")

    for i, raw_line in enumerate(lines, start=1):
        line = raw_line

        # URLマスク
        if mask_url:
            def _mask_url(m):
                logs.append({
                    "line_no": i, "action": "masked_url",
                    "field": "", "original": m.group(0)
                })
                return "[URL]"
            line = re.sub(r'https?://\S+', _mask_url, line)

        # 空行はスキップ
        if not line.strip():
            logs.append({
                "line_no": i, "action": "removed_empty_line",
                "field": "", "original": raw_line
            })
            continue

        m = kv_pattern.match(line)
        if m:
            key = m.group("key").strip()
            val = m.group("val").strip()

            # 個人情報フィールドに該当？
            if any(field in key for field in sensitive_fields):
                # 値が空 or 「様/さま」だけ
                if (val == "" or re.fullmatch(r"(様|さま)", val)):
                    logs.append({
                        "line_no": i, "action": "removed_sensitive_blank",
                        "field": key, "original": raw_line
                    })
                    continue
                else:
                    if pii_mode == "remove":
                        logs.append({
                            "line_no": i, "action": "removed_sensitive_field",
                            "field": key, "original": raw_line
                        })
                        continue
                    else:
                        # マスクして残す
                        logs.append({
                            "line_no": i, "action": "masked_sensitive_field",
                            "field": key, "original": raw_line
                        })
                        line = f"{key}： [MASKED]"

        # ここまで来たら残す
        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)
    return cleaned_text, logs


# =========================
# OpenAI応答の安全取り出し
# =========================
def get_content_or_none(resp):
    """
    Azure OpenAI のレスポンスから content を安全に取り出す。
    文字列かつ非空白のときのみ返し、それ以外は None。
    """
    try:
        if not resp or not getattr(resp, "choices", None):
            return None
        msg = getattr(resp.choices[0], "message", None)
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            s = content.strip()
            return s if s else None
        return None
    except Exception:
        return None


# =========================
# 環境変数 / OpenAI クライアント
# =========================
load_dotenv()
AZURE_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = "https://itg-llm-009-aoai-eastus-001.openai.azure.com/"
AZURE_OPENAI_API_VERSION = "2024-02-15-preview"
AZURE_OPENAI_DEPLOYMENT = "itg-llm-009-gpt-4o"

client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

# =========================
# Streamlit セットアップ
# =========================
st.set_page_config(page_title="市場調査企画アプリ", layout="wide")

# セッション状態
if "orien_text_raw" not in st.session_state:
    st.session_state.orien_text_raw = ""
if "orien_text_clean" not in st.session_state:
    st.session_state.orien_text_clean = ""
if "sanitize_logs" not in st.session_state:
    st.session_state.sanitize_logs = []
if "generated_sections" not in st.session_state:
    st.session_state.generated_sections = {}

#====================================================================
# タブ構成
tab1, tab2 = st.tabs(["オリエン議事読込", "KON下書き"])

# -------------------------
# タブ1：前処理の可視化
# -------------------------
with tab1:
    st.header("キックオフノートの下書きアプリ")
    st.subheader("手順1：オリエン議事録をアップロード")
    st.subheader("手順2：「KON下書き」タブへ移動してボタンを押す")
    # マニュアルリンク追加
    st.markdown(
        '[📖 詳しいマニュアルはこちら](https://delightful-river-09a986000.2.azurestaticapps.net)',
        unsafe_allow_html=True
    )
    uploaded_file = st.file_uploader("ファイルをアップロード（テキストファイルのみです）", type=["txt"])
    if uploaded_file is not None:
        raw = uploaded_file.read().decode("utf-8", errors="ignore")
        st.session_state.orien_text_raw = raw
        # 常に remove & mask_url=True を適用
        cleaned, logs = sanitize_input(raw, mask_url=True, pii_mode="remove")
        st.session_state.orien_text_clean = cleaned
        st.session_state.sanitize_logs = logs

    # 前処理後テキストのみ表示
    st.subheader("★個人情報を取り除く処理をした後の情報です★")
    st.text_area("この内容で下書きします", value=st.session_state.orien_text_clean, height=300)

    # ログ表示
    st.subheader("削除した個人情報のリスト（確認用）")
    if st.session_state.sanitize_logs:
        df = pd.DataFrame(st.session_state.sanitize_logs)
        st.dataframe(df, use_container_width=True)
        st.caption("action例: masked_url / removed_empty_line / removed_sensitive_blank / removed_sensitive_field / masked_sensitive_field")

        st.download_button(
            "🗂 前処理後テキストを保存",
            data=st.session_state.orien_text_clean,
            file_name=f"preprocessed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain"
        )
    else:
        st.info("ログはまだありません。ファイルをアップロードしてください。")


# -------------------------
# タブ2：生成と編集
# -------------------------
with tab2:
    st.header("✨ キックオフノートの下書き生成 ✨")

    # --- YAMLファイル読み込み関数 ---
    def load_kon_yaml():
        base_dir = os.path.dirname(__file__)
        yaml_path = os.path.join(base_dir, "kon.yaml")
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            st.error("kon.yaml が見つかりません。")
            return {}
        except yaml.YAMLError as e:
            st.error(f"YAMLの読み込み中にエラーが発生しました: {e}")
            return {}

    kon_prompts = load_kon_yaml()

    if st.session_state.orien_text_clean:
        st.success("前処理済みテキストが読み込まれています。")
    else:
        st.warning("オリエン議事読込を行ってから下書きしてください。")

    # --- 自動生成ボタン ---
    if st.session_state.orien_text_clean and kon_prompts and st.button("KONを下書き"):
        with st.spinner("Azure OpenAI が考え中..."):
            try:
                generated_sections = {}

                # --- 上位3項目 + ハイコンセプトを生成 ---
                for key in ["お客様名", "調査対象サービスや商品名", "ハイコンセプト"]:
                    item = kon_prompts.get(key, {}) or {}
                    premise = item.get("前提", "") or ""
                    instruction = item.get("指示", "") or ""
                    format_rule = item.get("出力形式", "") or ""

                    prompt = f"""
以下のオリエン情報を基に、{key}を定義してください。

# 前提:
{premise}

# 指示:
{instruction}

# 出力形式:
{format_rule}

# オリエン情報:
{st.session_state.orien_text_clean}
"""
                    resp = client.chat.completions.create(
                        model=AZURE_OPENAI_DEPLOYMENT,
                        messages=[
                            {"role": "system", "content": "あなたは市場調査のプロフェッショナルです。"},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=500
                    )
                    content = get_content_or_none(resp)
                    generated_sections[key] = content if content is not None else "(応答なし)"

                # --- ストーリーラインを生成 ---
                storyline_prompts = kon_prompts.get("ストーリーライン", {}) or {}
                storyline_texts = []
                for idx, (title, instruction) in enumerate(storyline_prompts.items(), start=1):
                    story_prompt = f"""
以下のオリエン情報を基に、{title}を定義してください。

# 指示:
{instruction}

# オリエン情報:
{st.session_state.orien_text_clean}
"""
                    story_resp = client.chat.completions.create(
                        model=AZURE_OPENAI_DEPLOYMENT,
                        messages=[
                            {"role": "system", "content": "あなたは市場調査のコンサルタントです。"},
                            {"role": "user", "content": story_prompt}
                        ],
                        temperature=0.7,
                        max_tokens=500
                    )
                    answer = get_content_or_none(story_resp)
                    storyline_texts.append(f"{idx}. {title}\n{answer if answer is not None else '(応答なし)'}\n")

                generated_sections["ストーリーライン"] = "\n".join(storyline_texts)

                # セッションに格納
                st.session_state.generated_sections = generated_sections

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

    # --- 編集可能エリア ---
    if st.session_state.generated_sections:
        st.subheader("✏️ キックオフノート（編集可）")
        edited_sections = {}

        for key in ["お客様名", "調査対象サービスや商品名", "ハイコンセプト"]:
            edited_sections[key] = st.text_area(
                f"🔹 {key}",
                value=st.session_state.generated_sections.get(key, ""),
                height=80 if key != "ハイコンセプト" else 200
            )

        edited_sections["ストーリーライン"] = st.text_area(
            "📘 ストーリーライン（編集可）",
            value=st.session_state.generated_sections.get("ストーリーライン", ""),
            height=400
        )

        export_content = ""
        for key, value in edited_sections.items():
            export_content += f"【{key}】\n{value}\n\n"

        st.download_button(
            label="💾 キックオフノートを保存",
            data=export_content,
            file_name=f"調査企画_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain"
        )
