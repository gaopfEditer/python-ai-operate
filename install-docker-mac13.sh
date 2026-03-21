#!/bin/bash

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BOLD}╔════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  Docker 环境安装脚本 (macOS 13)       ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════╝${NC}"
echo ""

# 检测系统架构
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    ARCH_TYPE="arm64"
    DOCKER_COMPOSE_ARCH="aarch64"
else
    ARCH_TYPE="amd64"
    DOCKER_COMPOSE_ARCH="x86_64"
fi

echo -e "📍 系统架构: ${BLUE}${ARCH_TYPE}${NC}"
echo ""

# 创建安装目录
INSTALL_DIR="$HOME/.local/bin"
mkdir -p "$INSTALL_DIR"

# 添加安装目录到 PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo -e "${YELLOW}⚠️  添加 $INSTALL_DIR 到 PATH...${NC}"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
    export PATH="$HOME/.local/bin:$PATH"
fi

echo ""
echo -e "${BOLD}[1/3] 安装 Colima...${NC}"

# 检查 colima 是否已安装
if command -v colima &> /dev/null; then
    # 验证 colima 是否真的可用（不是损坏的文件）
    if "$(which colima)" version &>/dev/null 2>&1; then
        echo -e "${GREEN}✅ Colima 已安装${NC}"
        colima version
    else
        echo -e "${YELLOW}⚠️  检测到损坏的 Colima 安装，将重新安装...${NC}"
        rm -f "$(which colima)" 2>/dev/null
        rm -f "$INSTALL_DIR/colima" 2>/dev/null
    fi
fi

# 如果 colima 未安装或已删除，则安装
if ! command -v colima &> /dev/null; then
    # 优先尝试使用 brew 安装
    if command -v brew &> /dev/null; then
        echo -e "${YELLOW}使用 Homebrew 安装 Colima...${NC}"
        if brew install colima 2>&1 | tee /tmp/brew-install.log; then
            echo -e "${GREEN}✅ Colima 通过 Homebrew 安装成功${NC}"
            colima version
        else
            echo -e "${YELLOW}⚠️  Homebrew 安装失败，尝试手动下载...${NC}"
            # 继续手动安装流程
        fi
    fi
    
    # 如果 brew 安装失败或不可用，提示用户
    if ! command -v colima &> /dev/null; then
        echo -e "${RED}❌ Colima 安装失败${NC}"
        echo -e "${YELLOW}请手动运行: brew install colima${NC}"
        exit 1
    fi
fi

echo ""
echo -e "${BOLD}[2/3] 安装 Docker...${NC}"

# 检查 docker 是否已安装
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✅ Docker 已安装${NC}"
    docker --version
else
    # 优先尝试使用 brew 安装
    if command -v brew &> /dev/null; then
        echo -e "${YELLOW}使用 Homebrew 安装 Docker CLI...${NC}"
        if brew install docker 2>&1 | tee /tmp/brew-docker.log; then
            echo -e "${GREEN}✅ Docker 通过 Homebrew 安装成功${NC}"
            docker --version
        else
            echo -e "${YELLOW}⚠️  Homebrew 安装失败，尝试手动下载...${NC}"
        fi
    fi
    
    # 如果 brew 安装失败或不可用，手动下载
    if ! command -v docker &> /dev/null; then
        echo -e "${YELLOW}正在手动下载 Docker CLI...${NC}"
        echo -e "${RED}❌ 手动下载 Docker CLI 较复杂，建议使用 Homebrew${NC}"
        echo -e "${YELLOW}提示: 运行 'brew install docker'${NC}"
        exit 1
    fi
fi

echo ""
echo -e "${BOLD}[3/3] 安装 Docker Compose...${NC}"

# 检查 docker-compose 是否已安装
if command -v docker-compose &> /dev/null; then
    echo -e "${GREEN}✅ Docker Compose 已安装${NC}"
    docker-compose --version
else
    # 优先尝试使用 brew 安装
    if command -v brew &> /dev/null; then
        echo -e "${YELLOW}使用 Homebrew 安装 Docker Compose...${NC}"
        if brew install docker-compose 2>&1 | tee /tmp/brew-compose.log; then
            echo -e "${GREEN}✅ Docker Compose 通过 Homebrew 安装成功${NC}"
            docker-compose --version
        else
            echo -e "${YELLOW}⚠️  Homebrew 安装失败，尝试手动下载...${NC}"
        fi
    fi
    
    # 如果 brew 安装失败或不可用，手动下载
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${YELLOW}正在手动下载 Docker Compose...${NC}"
        echo -e "${RED}❌ 手动下载 Docker Compose 较复杂，建议使用 Homebrew${NC}"
        echo -e "${YELLOW}提示: 运行 'brew install docker-compose'${NC}"
        exit 1
    fi
fi

echo ""
echo -e "${BOLD}╔════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║           安装完成！                   ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✅ 所有工具已安装完成${NC}"
echo ""
echo "📋 下一步操作:"
echo ""
echo "  1️⃣  重新加载 shell 配置:"
echo -e "     ${BLUE}source ~/.zshrc${NC}"
echo ""
echo "  2️⃣  启动 Colima:"
echo -e "     ${BLUE}colima start${NC}"
echo ""
echo "  3️⃣  验证安装:"
echo -e "     ${BLUE}docker --version${NC}"
echo -e "     ${BLUE}docker-compose --version${NC}"
echo ""
