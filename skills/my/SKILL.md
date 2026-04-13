
---
name: who_am_i
description: 当用户询问"我是谁"时，根据已记忆的用户信息生成个性化自我介绍
version: 1.0.0
author: user
---
# 触发条件

triggers:

- pattern: "我是谁"
  type: exact_match
- pattern: "介绍一下我自己"
  type: exact_match
- pattern: "关于我"
  type: exact_match

# 执行逻辑

steps:

1. 读取 memory_space 中关于用户的基本信息
2. 提取以下字段（如果存在）：
   - 姓名/昵称
   - 学校
   - 学历
   - 专业
   - 兴趣爱好
3. 生成友好、个性化的自我介绍回复

# 回复模板

response_template: |
  你好，**{name}**！👋

  你是 **{school}** 的一名{education}生，专业是 **{major}**。

  课余时间你喜欢 {hobbies}，是个热爱运动的学子！

  有什么我可以帮你的吗？

# 当前用户数据（从 memory_space 读取）

user_data:
  name: 小白
  school: 西安工业大学
  education: 本科
  major: 人工智能
  hobbies: 跑步、打乒乓球

# 错误处理

fallback: |
  你好！我记住了你的一些信息，但可能还不够完整。
  你能再告诉我一些关于你自己的事情吗？比如你的名字、学校、专业或兴趣爱好？
