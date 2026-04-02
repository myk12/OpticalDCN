import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

class AcademicStyleManager:
    def __init__(self):
        # Nordic Sci-Fi palette, good for up to 5 categories
        self.colors =   ['#0C4C8A', '#CE5C00', '#1D8E3E', '#75507B', '#555753']  
        self.markers = ['o', 's', '^', 'D']
        #self.font_family = font_family
        self._apply_global_settings()

    def _apply_global_settings(self):
        """初始化全局参数，强制所有图表拥有统一的黑色加粗全封闭边框"""
        plt.rcParams.update({
            #"font.family": self.font_family,
            #"font.serif": ["Times New Roman", "DejaVu Serif"],
            # --- 核心：全边框控制 ---
            "axes.linewidth": 1.2,          # 稍微加粗，让边框更有质感
            "axes.edgecolor": "black",      # 确保是纯黑
            "axes.spines.top": True,        # 强制保留顶边
            "axes.spines.right": True,      # 强制保留右边
            
            "patch.linewidth": 0.8,         # 柱状图本身的边框
            "xtick.direction": "in",        # 刻度向内是全边框标配
            "ytick.direction": "in",
            "xtick.top": True,              # 顶部也显示刻度（可选，更硬核）
            "ytick.right": True,            # 右侧也显示刻度
            
            "grid.linestyle": "--",
            "grid.alpha": 0.3,
            "figure.dpi": 300,
            "savefig.bbox": "tight",
            "legend.frameon": True,         # 这种风格通常配有边框的图例
            "legend.edgecolor": "black",

            # font size
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 9,
        })

    def get_palette(self, levels):
        return dict(zip(sorted(levels), self.colors[:len(levels)]))

    def get_markers(self, levels):
        return dict(zip(sorted(levels), self.markers[:len(levels)]))

    def finalize_axes(self, ax, title=None, xlabel=None, ylabel=None, is_log=False):
        """处理标签和坐标轴，不再执行 despine"""
        if title: ax.set_title(title, fontweight='bold', pad=12)
        if xlabel: ax.set_xlabel(xlabel)
        if ylabel: ax.set_ylabel(ylabel)
        
        # 确保四周的线条都是黑色的（防止被 Seaborn 默认主题覆盖）
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_edgecolor('black')
        
        if is_log:
            ax.set_yscale('log')
            from matplotlib.ticker import LogFormatterMathtext
            ax.yaxis.set_major_formatter(LogFormatterMathtext())
            
        return ax