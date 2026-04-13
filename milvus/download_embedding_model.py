
"""
先运行
pip install modelscope
或者 命令行运行
python -c "
from modelscope import snapshot_download
import os

# 创建模型目录
model_dir = 'milvus/embedding_model'
os.makedirs(model_dir, exist_ok=True)

# 下载模型
print('开始下载模型...')
model_path = snapshot_download('iic/nlp_corom_sentence-embedding_chinese-base', cache_dir=model_dir)
print(f'模型下载完成: {model_path}')
"
"""

#pip install modelscope
# download_embedding_model.py
from modelscope import snapshot_download
import os

def main():
    # 模型保存目录
    model_dir = 'milvus/embedding_model'
    os.makedirs(model_dir, exist_ok=True)

    print("开始下载中文句向量模型：iic/nlp_corom_sentence-embedding_chinese-base")
    model_path = snapshot_download(
        'iic/nlp_corom_sentence-embedding_chinese-base',
        cache_dir=model_dir
    )
    print(f"模型下载完成！路径：{model_path}")

if __name__ == '__main__':
    main()