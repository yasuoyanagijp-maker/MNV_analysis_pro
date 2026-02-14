"""
ARIAKE OCTA Analysis - Streamlit Web Application
"""
import streamlit as st
import sys
from pathlib import Path

# プロジェクトルートをsys.pathに追加
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import tempfile
import shutil
from datetime import datetime
import traceback
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import io
import numpy as np
import cv2
import zipfile
import os

from core.vd_analysis import VDAnalyzer
from core.mnv_pipeline import MNVBatchAnalyzer, MNVPipeline
# ページ設定
st.set_page_config(
    page_title="ARIAKE OCTA Analysis",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        font-weight: bold;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
    }
    </style>
""", unsafe_allow_html=True)


def initialize_session_state():
    """セッション状態を初期化"""
    if 'analysis_running' not in st.session_state:
        st.session_state.analysis_running = False
    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'log_messages' not in st.session_state:
        st.session_state.log_messages = []


def add_log(message: str):
    """ログメッセージを追加"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.log_messages.append(f"[{timestamp}] {message}")

def extract_roi_from_canvas(canvas_data, original_size):
    """Canvas の輪郭線から「内側が塗られた ROI マスク」を作る"""
    if canvas_data is None:
        return None

    # 1. 緑チャンネルを取得（描いた線が緑の前提）
    green = canvas_data[:, :, 1].astype(np.uint8)

    # 2. 線を強調するために2値化
    #    元画像の緑成分の影響を減らしたい場合は閾値を少し高めに
    _, line_bin = cv2.threshold(green, 50, 255, cv2.THRESH_BINARY)

    # 3. 輪郭を抽出
    contours, _ = cv2.findContours(line_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # 4. 真っ黒なマスクを用意し、輪郭の内側を塗りつぶす
    #    Canvasサイズ基準で作り、その後リサイズ
    h, w = green.shape
    mask_canvas = np.zeros((h, w), dtype=np.uint8)

    # 全ての輪郭を塗りつぶし（thickness=-1）
    cv2.drawContours(mask_canvas, contours, -1, color=255, thickness=-1)

    # 5. 元画像サイズにリサイズ
    if mask_canvas.shape != (original_size[1], original_size[0]):
        mask_canvas = cv2.resize(mask_canvas, original_size, interpolation=cv2.INTER_NEAREST)

    return mask_canvas

def display_single_image_mode_with_roi(scale_mm: float, save_stages: bool):
    """ROI選択機能付きの単一画像解析（ROI選択必須）"""
    st.header("🎯 Single Image Analysis with ROI Selection")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Upload MNV Image",
            type=['tif', 'tiff', 'png', 'jpg', 'jpeg'],
            help="Select the MNV image to analyze",
            key="roi_image"
        )
    
    with col2:
        st.markdown("**ROI Selection Mode**")
        st.write("✏️ Manual Selection (required)")
    
    if uploaded_file is not None:
        image_bytes = uploaded_file.read()
        
        # ROI未選択時のみ描画インターフェースを表示
        if not st.session_state.roi_selected:
            st.subheader("Step 1: Draw ROI on the Image")
            st.info("💡 Click and drag to draw a freehand region around the MNV lesion.")
            
            pil_image = Image.open(io.BytesIO(image_bytes))
            
            canvas_result = st_canvas(
                fill_color="rgba(0, 255, 0, 0.3)",
                stroke_width=2,
                stroke_color="#00FF00",
                background_image=pil_image,
                update_streamlit=True,
                drawing_mode="freedraw",
                point_display_radius=0,
                key="canvas",
                height=min(pil_image.height, 600),
                width=min(pil_image.width, 800),
            )
            
            col_a, col_b = st.columns([1, 1])
            
            with col_a:
                if st.button("✅ Confirm ROI", type="primary", use_container_width=True):
                    if canvas_result.image_data is not None:
                        roi_mask = extract_roi_from_canvas(canvas_result.image_data, pil_image.size)
                        
                        if roi_mask is not None and roi_mask.sum() > 0:
                            st.session_state.roi_selected = True
                            st.session_state.current_roi_mask = roi_mask
                            st.session_state.current_image_bytes = image_bytes
                            st.success("✅ ROI confirmed successfully!")
                            st.rerun()
                        else:
                            st.error("❌ Please draw an ROI on the image first")
                    else:
                        st.error("❌ Please draw an ROI on the image first")
            
            with col_b:
                if st.button("🔄 Start Over", use_container_width=True):
                    st.session_state.roi_selected = False
                    st.session_state.current_roi_mask = None
                    st.rerun()
        
        # ROI 確認後に解析ボタンを表示
        else:
            st.markdown("---")
            st.subheader("Step 2: Execute Analysis")
            st.success("✅ ROI is ready. Proceed to analysis.")
            
            col_x, col_y = st.columns([2, 1])
            
            with col_x:
                if st.button("🚀 Analyze with Custom ROI", type="primary", use_container_width=True):
                    analyze_with_custom_roi(
                        st.session_state.current_image_bytes,
                        st.session_state.current_roi_mask,
                        scale_mm,
                        save_stages
                    )
            
            with col_y:
                if st.button("🔄 Change ROI", use_container_width=True):
                    st.session_state.roi_selected = False
                    st.session_state.current_roi_mask = None
                    st.rerun()

def analyze_single_image(mnv_file, cc_file, scale_mm, save_stages):
    """単一画像を解析"""
    st.session_state.log_messages = []
    add_log("Starting single image analysis...")
    
    # 進捗表示
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # 一時ディレクトリ作成
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # MNV画像を保存
            mnv_path = temp_path / mnv_file.name
            with open(mnv_path, 'wb') as f:
                f.write(mnv_file.getbuffer())
            
            add_log(f"Saved MNV image: {mnv_file.name}")
            progress_bar.progress(20)
            
            # CC画像を保存（あれば）
            cc_path = None
            if cc_file is not None:
                cc_path = temp_path / cc_file.name
                with open(cc_path, 'wb') as f:
                    f.write(cc_file.getbuffer())
                add_log(f"Saved CC image: {cc_file.name}")
            
            progress_bar.progress(30)
            status_text.text("Analyzing image...")
            
            # 解析実行
            pipeline = MNVPipeline(
                scale_mm=scale_mm,
                save_stages=save_stages
            )
            
            output_dir = temp_path / "output"
            output_dir.mkdir(exist_ok=True)
            
            results = pipeline.analyze(
                image_path=str(mnv_path),
                output_dir=str(output_dir),
                flow_deficit_image_path=str(cc_path) if cc_path else None
            )
            
            progress_bar.progress(90)
            add_log("Analysis completed successfully!")
            
            # 結果を表示
            display_single_image_results(results, output_dir)
            
            progress_bar.progress(100)
            status_text.empty()
            
            st.success("✅ Analysis completed successfully!")
    
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        add_log(f"Error: {str(e)}")
        with st.expander("Error Details"):
            st.code(traceback.format_exc())


def analyze_batch(uploaded_files, analysis_type, scale_mm, save_stages,
                 vd_side, sup_suffix, deep_suffix, mnv_suffix, cc_suffix):
    """バッチ解析を実行"""
    st.session_state.log_messages = []
    add_log("Starting batch analysis...")
    
    # 進捗表示
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # 一時ディレクトリ作成
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_dir = temp_path / "input"
            output_dir = temp_path / "output"
            input_dir.mkdir(exist_ok=True)
            output_dir.mkdir(exist_ok=True)
            
            # ファイルを保存
            status_text.text("Uploading files...")
            for i, file in enumerate(uploaded_files):
                file_path = input_dir / file.name
                with open(file_path, 'wb') as f:
                    f.write(file.getbuffer())
                progress_bar.progress(int((i + 1) / len(uploaded_files) * 20))
            
            add_log(f"Uploaded {len(uploaded_files)} files")
            
            # VD解析
            if analysis_type in ["VD Analysis", "Both"]:
                status_text.text("Running VD Analysis...")
                add_log("Starting VD Analysis...")
                
                vd_analyzer = VDAnalyzer(
                    input_dir=str(input_dir),
                    output_dir=str(output_dir / "VD"),
                    scale_mm=scale_mm,
                    side=vd_side,
                    sup_suffix=sup_suffix,
                    deep_suffix=deep_suffix,
                    save_stages=save_stages
                )
                
                vd_results = vd_analyzer.analyze()
                progress_bar.progress(50)
                add_log(f"VD Analysis completed: {len(vd_results.get('patient_ids', []))} files")
            
            # MNV解析
            if analysis_type in ["MNV Analysis", "Both"]:
                status_text.text("Running MNV Analysis...")
                add_log("Starting MNV Analysis...")
                
                mnv_analyzer = MNVBatchAnalyzer(
                    input_dir=str(input_dir),
                    output_dir=str(output_dir / "MNV"),
                    scale_mm=scale_mm,
                    mnv_suffix=mnv_suffix,
                    cc_suffix=cc_suffix,
                    save_stages=save_stages
                )
                
                mnv_results = mnv_analyzer.analyze()
                progress_bar.progress(90)
                add_log(f"MNV Analysis completed: {len(mnv_results.get('patient_ids', []))} files")
            
            # 結果をセッションに保存
            st.session_state.results = {
                'vd': vd_results if analysis_type in ["VD Analysis", "Both"] else None,
                'mnv': mnv_results if analysis_type in ["MNV Analysis", "Both"] else None,
                'output_dir': output_dir
            }
            
            # 結果ファイルをダウンロード可能にする
            prepare_download_files(output_dir)
            
            progress_bar.progress(100)
            status_text.empty()
            add_log("All analysis completed successfully!")
            
            st.success("✅ Analysis completed successfully!")
    
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        add_log(f"Error: {str(e)}")
        with st.expander("Error Details"):
            st.code(traceback.format_exc())


def display_single_image_results(results: dict, output_dir: Path):
    """単一画像の結果を表示（詳細表示 + 画像 + ダウンロード）"""
    st.header("📊 Analysis Results")
    
    # メトリクス表示（上部に4カラム）
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("MNV Area", f"{results.get('mnv_area_mm2', 0):.3f} mm²")
    
    with col2:
        st.metric("Vessel Density", f"{results.get('vessel_density', 0) * 100:.2f} %")
    
    with col3:
        st.metric("Complexity Score", f"{results.get('complexity_score', 0):.1f}")
    
    with col4:
        st.metric("Subtype", results.get('mnv_subtype', 'Unknown'))
    
    # 詳細結果（Tab付き）
    st.markdown("---")
    with st.expander("📋 Detailed Results", expanded=True):
        tab1, tab2, tab3 = st.tabs(["Basic Metrics", "Spatial Distribution", "Flow Deficit"])
        
        with tab1:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Vessel Metrics")
                st.write(f"**Vessel Length:** {results.get('vessel_length_mm', 0):.3f} mm")
                st.write(f"**Mean Diameter:** {results.get('mean_diameter_um', 0):.2f} μm")
                st.write(f"**Tortuosity:** {results.get('tortuosity', 0):.3f}")
                st.write(f"**Fractal Dimension:** {results.get('fractal_dimension', 0):.3f}")
            
            with col2:
                st.subheader("Network Metrics")
                st.write(f"**Branches:** {results.get('num_branches', 0)}")
                st.write(f"**Junctions:** {results.get('num_junctions', 0)}")
                st.write(f"**Endpoints:** {results.get('num_endpoints', 0)}")
                st.write(f"**Loops:** {results.get('num_loops', 0)}")
        
        with tab2:
            st.subheader("Spatial Distribution")
            st.write(f"**Trunk Pattern:** {results.get('trunk_pattern', 'Unknown')}")
            st.write(f"**Trunk Eccentricity:** {results.get('trunk_eccentricity', -1):.3f}")
            st.write(f"**Stability Score:** {results.get('stability_score', 0):.1f}")
            st.write(f"**Maturity Index:** {results.get('maturity_index', 0):.1f}")
        
        with tab3:
            st.subheader("Flow Deficit")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write("**Ring 1**")
                st.write(f"FD%: {results.get('FD_percent_R1', 0):.2f}%")
                st.write(f"Count: {results.get('FD_number_R1', 0)}")
            
            with col2:
                st.write("**Ring 2**")
                st.write(f"FD%: {results.get('FD_percent_R2', 0):.2f}%")
                st.write(f"Count: {results.get('FD_number_R2', 0)}")
            
            with col3:
                st.write("**Ring 3**")
                st.write(f"FD%: {results.get('FD_percent_R3', 0):.2f}%")
                st.write(f"Count: {results.get('FD_number_R3', 0)}")
    
    # 画像表示
    st.markdown("---")
    if output_dir.exists():
        image_files = list(output_dir.glob("*.png")) + list(output_dir.glob("*.jpg"))
        
        if image_files:
            st.subheader("🖼️ Result Images")
            
            for img_file in image_files:
                st.image(str(img_file), caption=img_file.name, use_column_width=True)
            
            # ZIP ダウンロード機能
            st.markdown("---")
            st.subheader("📦 Download Pipeline Images (ZIP)")
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for img_file in image_files:
                    zipf.write(
                        img_file,
                        arcname=os.path.basename(img_file)
                    )
            zip_buffer.seek(0)
            st.download_button(
                label="💾 Download pipeline images (ZIP)",
                data=zip_buffer,
                file_name="pipeline_images.zip",
                mime="application/zip",
            )


def display_results():
    """バッチ解析の結果を表示"""
    st.header("📊 Analysis Results")
    
    results = st.session_state.results
    
    # VD結果
    if results.get('vd') is not None:
        vd_data = results['vd']
        
        with st.expander("🔵 VD Analysis Results", expanded=True):
            st.write(f"**Processed:** {len(vd_data.get('patient_ids', []))} files")
            
            # データフレーム表示
            import pandas as pd
            
            df = pd.DataFrame({
                'Patient ID': vd_data.get('patient_ids', []),
                'FAZ Area (mm²)': vd_data.get('faz_areas', []),
                'Circularity': vd_data.get('faz_circularities', []),
                'Superficial (%)': vd_data.get('superficial_whole', []),
                'Deep (%)': vd_data.get('deep_whole', [])
            })
            
            st.dataframe(df, use_container_width=True)
    
    # MNV結果
    if results.get('mnv') is not None:
        mnv_data = results['mnv']
        
        with st.expander("🔴 MNV Analysis Results", expanded=True):
            st.write(f"**Processed:** {len(mnv_data.get('patient_ids', []))} files")
            
            # データフレーム表示
            import pandas as pd
            
            df = pd.DataFrame({
                'Patient ID': mnv_data.get('patient_ids', []),
                'Subtype': mnv_data.get('mnv_subtypes', []),
                'MNV Area (mm²)': mnv_data.get('mnv_areas', []),
                'Vessel Density (%)': [v * 100 for v in mnv_data.get('vessel_densities', [])],
                'Complexity': mnv_data.get('complexity_scores', []),
                'Stability': mnv_data.get('stability_scores', [])
            })
            
            st.dataframe(df, use_container_width=True)


def prepare_download_files(output_dir: Path):
    """ダウンロード用にファイルを準備"""
    st.subheader("📥 Download Results")

    # CSV ファイル
    csv_files = list(output_dir.rglob("*.csv"))
    if csv_files:
        col1, col2 = st.columns(2)
        for i, csv_file in enumerate(csv_files):
            with open(csv_file, 'rb') as f:
                csv_data = f.read()
            col = col1 if i % 2 == 0 else col2
            with col:
                st.download_button(
                    label=f"📄 {csv_file.name}",
                    data=csv_data,
                    file_name=csv_file.name,
                    mime="text/csv"
                )

    # ★ パイプライン画像（PNG/JPG）をまとめて zip ダウンロード
    image_files = list(output_dir.rglob("*.png")) + list(output_dir.rglob("*.jpg"))
    if image_files:
        st.subheader("📦 Download Pipeline Images (ZIP)")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for img_file in image_files:
                zipf.write(
                    img_file,
                    arcname=img_file.relative_to(output_dir)  # サブフォルダ構造も維持したい場合
                )
        zip_buffer.seek(0)
        st.download_button(
            label="💾 Download all pipeline images (ZIP)",
            data=zip_buffer,
            file_name="pipeline_images_batch.zip",
            mime="application/zip",
        )



def extract_roi_from_canvas(canvas_data, original_size):
    """Canvas データから ROI マスクを抽出"""
    import numpy as np
    import cv2
    
    # Canvas データ（RGBA）から緑チャンネルを取得（描画部分）
    if canvas_data is None:
        return None
    
    # 緑色の描画部分を抽出
    green_channel = canvas_data[:, :, 1]
    
    # 閾値処理で ROI を抽出
    roi_mask = (green_channel > 0).astype(np.uint8) * 255
    
    # 元の画像サイズにリサイズ
    if roi_mask.shape[:2] != original_size[::-1]:
        roi_mask = cv2.resize(roi_mask, original_size, interpolation=cv2.INTER_NEAREST)
    
    return roi_mask


def analyze_with_custom_roi(image_bytes, roi_mask, scale_mm, save_stages):
    """カスタムROIを使用して解析"""
    st.session_state.log_messages = []
    add_log("Starting analysis with custom ROI...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # 画像を保存
            image_path = temp_path / "input_image.tif"
            with open(image_path, 'wb') as f:
                f.write(image_bytes)
            
            add_log(f"Saved image: {image_path.name}")
            progress_bar.progress(20)
            
            # ROI マスクを保存
            roi_path = temp_path / "roi_mask.png"
            import cv2
            cv2.imwrite(str(roi_path), roi_mask)
            add_log("ROI mask created")
            
            progress_bar.progress(30)
            status_text.text("Analyzing with custom ROI...")
            
            # MNV Pipeline で解析
            from core.mnv_pipeline import MNVPipeline
            
            pipeline = MNVPipeline(
                scale_mm=scale_mm,
                save_stages=save_stages
            )
            
            output_dir = temp_path / "output"
            output_dir.mkdir(exist_ok=True)
            
            # 画像とROIマスクを読み込み
            import cv2
            image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
            
            # ROI を適用して解析
            results = pipeline.analyze(
                image_path=str(image_path),
                roi_mask=roi_mask,
                output_dir=str(output_dir),
            )
            
            progress_bar.progress(90)
            add_log("Analysis completed successfully!")
            
            # 結果を表示
            display_single_image_results(results, output_dir)
            
            progress_bar.progress(100)
            status_text.empty()
            
            st.success("✅ Analysis completed successfully with custom ROI!")
    
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        add_log(f"Error: {str(e)}")
        with st.expander("Error Details"):
            st.code(traceback.format_exc())

def main():
    """メイン関数"""
    initialize_session_state()
    
    # ヘッダー
    st.markdown('<div class="main-header">🔬 ARIAKE OCTA Analysis System</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Python Implementation v2.0</div>', unsafe_allow_html=True)
    
    # サイドバー - 設定
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # 解析タイプ選択
        analysis_type = st.selectbox(
            "Analysis Type",
            ["VD Analysis", "MNV Analysis", "Both", "Single MNV Image"],
            help="Select the type of analysis to perform"
        )
        
        st.divider()
        
        # 基本設定
        st.subheader("Basic Settings")
        
        scale_mm = st.number_input(
            "Image Scale (mm)",
            min_value=1.0,
            max_value=20.0,
            value=6.0,
            step=0.5,
            help="Physical size of the image in millimeters"
        )
        
        save_stages = st.checkbox(
            "Save intermediate stages",
            value=False,
            help="Save intermediate processing images"
        )
        
        st.divider()
        
        # VD設定
        if analysis_type in ["VD Analysis", "Both"]:
            st.subheader("VD Settings")
            
            vd_side = st.selectbox("Eye Side", ["right", "left"])
            sup_suffix = st.text_input("Superficial Suffix", "1.tif")
            deep_suffix = st.text_input("Deep Suffix", "2.tif")
        
        # MNV設定
        if analysis_type in ["MNV Analysis", "Both", "Single MNV Image"]:
            st.subheader("MNV Settings")
            
            mnv_suffix = st.text_input("MNV Image Suffix", "3.tif")
            cc_suffix = st.text_input("CC Image Suffix", "4.tif")
    
    # メインエリア
    if analysis_type == "Single MNV Image":
        display_single_image_mode_with_roi(scale_mm, save_stages)
    else:
        # TODO: display_batch_mode は未実装のため一時的にコメントアウト
        # display_batch_mode(
        #     analysis_type,
        #     scale_mm,
        #     save_stages,
        #     vd_side if analysis_type in ["VD Analysis", "Both"] else None,
        #     sup_suffix if analysis_type in ["VD Analysis", "Both"] else None,
        #     deep_suffix if analysis_type in ["VD Analysis", "Both"] else None,
        #     mnv_suffix if analysis_type in ["MNV Analysis", "Both"] else None,
        #     cc_suffix if analysis_type in ["MNV Analysis", "Both"] else None
        # )
        st.info("Batch mode is not yet implemented. Please use Single MNV Image mode.")


if __name__ == "__main__":
    main()