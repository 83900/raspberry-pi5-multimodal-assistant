# E5 视觉意图文章：配图与插入说明

## 配图位置

### 题图

文件：`images/e5-vision-intent-cover.png`

建议作为公众号封面，不需要图注。

### 图 1：E5 ONNX 与分类头如何组合

文件：`images/e5-head-pipeline.png`

建议放在正文“整体结构大致如下所示”之后。

图注：**E5 ONNX 只负责生成 384 维 embedding，分类头在 ONNX 输出端完成概率计算。**

### 图 2：高维语义空间

文件：`images/e5-semantic-space.png`

建议放在面向入门读者的高维向量解释之后。

图注：**二维投影示意。真实 embedding 为 384 维，线性分类器学习的是超平面，而不是二维图中的一条线。**

### 图 3：树莓派短生命周期 worker

文件：`images/e5-worker-memory.png`

建议放在“2.2 E5 不常驻问题”中，位于 worker 流程之后。

图注：**分类时短暂加载 E5，完成后退出 worker，用约 2 秒分类耗时换回约 900MB 常驻内存。**

### 图 4：实机分类结果

文件：`images/e5-results.png`

建议放在“3. 测试”的分类器表格之前或直接替代表格。

图注：**0.50 为当前默认阈值；challenge 集更能反映困难样本上的真实效果。**

---

## 可直接插入正文：分类头到底怎么和 E5 ONNX 组合？

需要先澄清一点：训练出的分类头并没有被写进 E5 的 ONNX 文件，两者在磁盘上仍然是独立的。

项目部署时一共需要三类文件：

```text
model.onnx                 E5 Transformer 编码器
tokenizer.json             与 E5 配套的 tokenizer
vision_intent_head.npz     我训练出的线性分类头
```

训练阶段，SentenceTransformers 先把每句话编码成 384 维、经过 L2 归一化的 embedding。Logistic Regression 在这些向量上学习出 384 个权重和一个偏置：

```text
weight.shape = [384]
bias.shape   = []
```

训练完成后，程序从 scikit-learn 模型中取出 `coef_` 和 `intercept_`，再把它们连同判断阈值保存进 `vision_intent_head.npz`。因此树莓派部署时不再需要 scikit-learn。

推理阶段的组合发生在 Python worker 里：

```python
# 1. E5 ONNX 输出每个 token 的 384 维隐藏状态
hidden = session.run(None, inputs)[0]

# 2. 按 attention mask 做 mean pooling，再进行 L2 归一化
pooled = (
    hidden * attention_mask[..., None]
).sum(axis=1) / attention_mask.sum(axis=1, keepdims=True)
pooled /= np.linalg.norm(pooled, axis=1, keepdims=True)

# 3. 读取单独保存的分类头
head = np.load("vision_intent_head.npz")
weight = head["weight"]
bias = float(head["bias"])

# 4. 完成 Logistic Regression 的前向计算
logit = float(pooled[0] @ weight + bias)
probability = 1.0 / (1.0 + np.exp(-logit))
capture = probability >= float(head["capture_threshold"])
```

其中 `pooled[0] @ weight` 是两个 384 维向量的点积，结果是一个标量；加上 `bias` 后得到 `logit`，再经过 sigmoid 转成 0 到 1 之间的概率。最后把概率与阈值比较，得到“拍照”或“不拍照”。

换句话说，这不是把两个神经网络拼成一个大模型，而是：

```text
E5 ONNX 负责提取特征
             +
NPZ 分类头负责解释这些特征
             =
一次完整的视觉意图判断
```

这也解释了为什么分类头只有几 KB：E5 已经完成了绝大多数语言理解工作，分类头只需要在固定的 384 维空间里找到一个决策超平面。

### 必须保持一致的四件事

训练和部署必须使用：

1. 同一个 E5 checkpoint；
2. 同一个 tokenizer；
3. 同样的 `query: ` 前缀；
4. 同样的 mean pooling 和 L2 归一化。

任何一项不一致，分类头面对的向量空间都会发生变化。即使维度仍然是 384，原来训练出来的权重也可能失效。

当前 `.npz` 还保存了 `ask_threshold`，但现有 worker 实际只读取 `capture_threshold`；`ask_threshold` 是为以后增加“不确定时询问用户”预留的，目前没有参与决策。

---

## 正文中建议修正的技术表述

1. 模型名应为 `intfloat/multilingual-e5-small`，原文少了最后一个 `l`。
2. “文字意图判断模型早在 2016 年才诞生”并不准确。文本分类和意图识别更早就存在；如果指 Transformer，论文发表于 2017 年。
3. 高维空间并不意味着“句子有微小差异就一定相距很远”。E5 的目标恰恰是让语义相似的文本距离更近，即使它们用词不同。
4. “分类器使用一根线”适合作为二维比喻；严格来说，它在 384 维空间中学习的是一个超平面。
5. 约 901–904MB 的最大 RSS 来自当前 Raspberry Pi 实机测试，不是 Mac 测试。
6. challenge 集的准确率为 91.5%，正文可以写“约 92%”，但表格中建议保留精确值。

建议将入门解释改成：

> E5 会把一句话压缩成一个 384 维向量。这个向量不是简单记录关键词，而是尽量保留整句话的语义：意思接近的句子通常会落在相邻区域，即使中英文表达或具体用词不同。随后，线性分类头在这个空间里学习一个决策超平面，把“回答依赖当前画面”和“可以直接用文字回答”分开。图里画成二维的一条线只是方便理解，真实计算发生在 384 维空间。
