import streamlit as st
import os
from openai import AzureOpenAI
from dotenv import load_dotenv
from io import StringIO
from datetime import datetime
import yaml
import openpyxl
import pandas as pd
from io import BytesIO


# 環境変数読み込み
load_dotenv()

# Azure OpenAI 接続情報
AZURE_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = "https://itg-llm-009-aoai-eastus-001.openai.azure.com/"
AZURE_OPENAI_API_VERSION = "2024-02-15-preview"
AZURE_OPENAI_DEPLOYMENT = "itg-llm-009-gpt-4o"

# クライアント初期化
client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

# セッション状態
st.set_page_config(page_title="市場調査企画アプリ", layout="wide")
if "orien_text" not in st.session_state:
    st.session_state.orien_text = ""
if "concept_text" not in st.session_state:
    st.session_state.concept_text = ""
if "storyline_text" not in st.session_state:
    st.session_state.storyline_text = ""



#====================================================================
# タブ構成
tab1, tab2 = st.tabs(["引合情報", "KON"])

# --- タブ1：オリエン情報入力 ---
with tab1:
    st.header("📝 オリエンテーション情報をアップロード")
    uploaded_file = st.file_uploader("ファイルをアップロード（txtのみ）", type=["txt"])

    if uploaded_file is not None:
        content = uploaded_file.read().decode("utf-8")
        st.session_state.orien_text = content
        st.text_area("読み込んだ内容（編集可）", value=content, height=300)

#====================================================================
# --- タブ2：生成と編集 ---
with tab2:
    st.header("✨ キックオフノート作成")

    # --- YAMLファイル読み込み関数 ---
    def load_kon_yaml():
        """
        kon.yaml を読み込む。
        """
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

    # YAMLの読み込み
    kon_prompts = load_kon_yaml()

    # --- 自動生成ボタン ---
    if st.session_state.orien_text and kon_prompts and st.button("調査企画を生成"):
        with st.spinner("Azure OpenAI に問い合わせ中..."):
            try:
                generated_sections = {}

                # --- 上位3項目 + ハイコンセプトを生成 ---
                for key in ["お客様名", "調査対象サービスや商品名", "ハイコンセプト"]:
                    item = kon_prompts.get(key, {})
                    premise = item.get("前提", "")
                    instruction = item.get("指示", "")
                    format_rule = item.get("出力形式", "")

                    prompt = f"""
以下のオリエン情報を基に、{key}を定義してください。

# 前提:
{premise}

# 指示:
{instruction}

# 出力形式:
{format_rule}

# オリエン情報:
{st.session_state.orien_text}



"""
                    response = client.chat.completions.create(
                        model=AZURE_OPENAI_DEPLOYMENT,
                        messages=[
                            {"role": "system", "content": "あなたは市場調査のプロフェッショナルです。"},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=500
                    )
                    generated_sections[key] = response.choices[0].message.content.strip()

                # --- ストーリーラインを生成 ---
                storyline_prompts = kon_prompts.get("ストーリーライン", {})
                storyline_texts = []
                for idx, (title, instruction) in enumerate(storyline_prompts.items(), start=1):
                    story_prompt = f"""
以下のオリエン情報を基に、{title}を定義してください。

# 指示:
{instruction}

# オリエン情報:
{st.session_state.orien_text}
"""
                    story_response = client.chat.completions.create(
                        model=AZURE_OPENAI_DEPLOYMENT,
                        messages=[
                            {"role": "system", "content": "あなたは市場調査のコンサルタントです。"},
                            {"role": "user", "content": story_prompt}
                        ],
                        temperature=0.7,
                        max_tokens=500
                    )
                    answer = story_response.choices[0].message.content.strip()
                    storyline_texts.append(f"{idx}. {title}\n{answer}\n")

                generated_sections["ストーリーライン"] = "\n".join(storyline_texts)

                # セッションに格納
                st.session_state.generated_sections = generated_sections

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

    # --- 編集可能エリア ---
    if "generated_sections" in st.session_state and st.session_state.generated_sections:
        st.subheader("✏️ キックオフノート（編集可）")
        edited_sections = {}

        # 上位3項目 + ハイコンセプト
        for key in ["お客様名", "調査対象サービスや商品名", "ハイコンセプト"]:
            edited_sections[key] = st.text_area(
                f"🔹 {key}", 
                value=st.session_state.generated_sections.get(key, ""), 
                height=80 if key != "ハイコンセプト" else 200
            )

        # ストーリーライン
        edited_sections["ストーリーライン"] = st.text_area(
            "📘 ストーリーライン（編集可）",
            value=st.session_state.generated_sections.get("ストーリーライン", ""),
            height=400
        )

        # --- 保存機能 ---
        # --- 保存機能 ---
        export_content = ""
        for key, value in edited_sections.items():
            export_content += f"【{key}】\n{value}\n\n"

        # ダウンロードボタンとして利用（押したら即ダウンロード）
        st.download_button(
            label="💾 キックオフノートを保存",
            data=export_content,
            file_name=f"調査企画_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain"
        )

