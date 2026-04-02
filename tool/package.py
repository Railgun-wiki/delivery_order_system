import os
import subprocess
import tarfile

def main():
    # 确保我们在项目根目录下运行
    tool_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(tool_dir)
    os.chdir(project_root)

    output_archive = "project_release.tar.gz"

    print("正在获取 Git 追踪的文件列表...")
    try:
        # 仅获取 git 仓库内的真实文件清单
        result = subprocess.run(
            ["git", "ls-files"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        tracked_files = result.stdout.splitlines()
    except subprocess.CalledProcessError as e:
        print(f"运行 git ls-files 失败，请确保当前处于 Git 仓库根目录。错误: {e}")
        return

    print(f"正在打包为 {output_archive} ...")
    with tarfile.open(output_archive, "w:gz") as tar:
        # 将所有 git 包含的文件按原路径打包
        for file_path in tracked_files:
            if os.path.exists(file_path):
                tar.add(file_path, arcname=file_path)
        
        # 将要求的文档复制到压缩包根目录
        docs_to_root = [
            "doc/ai-chat-history.md",
            "doc/design.md"
        ]
        
        for doc in docs_to_root:
            if os.path.exists(doc):
                root_name = os.path.basename(doc)
                print(f"正在将 {doc} 映射到压缩包根目录作为 {root_name}...")
                tar.add(doc, arcname=root_name)

    print(f"打包完成，已生成压缩包：{output_archive}")

if __name__ == "__main__":
    main()
