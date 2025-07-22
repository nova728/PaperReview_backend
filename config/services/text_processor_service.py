import logging
from typing import Dict, Any, List, Optional, Generator
import re

logger = logging.getLogger(__name__)

class TextProcessorService:
    MAX_LENGTH = 32768  # 32k字符限制
    CHUNK_SIZE = 16000  # 16k字符块
    CHUNK_OVERLAP = 500  # 块重叠500字符
    
    def __init__(self, include_authors=False):
        """
        初始化文本处理服务
        
        Args:
            include_authors (bool): 是否包含作者信息，默认False
                                  对于peer review，建议设为False以避免偏见
        """
        self.include_authors = include_authors
    
    def process_paper_json(self, paper_json: Dict[str, Any], auto_truncate: bool = True) -> str:
        """
        JSON论文转文本
        
        Args:
            paper_json: 论文JSON数据
            auto_truncate: 是否自动截断到最大长度，默认True
                          设为False时返回完整文本，由调用者决定是否需要分块处理
        """
        logger.info("处理JSON格式论文数据")
        
        try:
            text_parts = []
            
            # 处理标题
            title = self._extract_title(paper_json)
            if title:
                text_parts.append(f"Title: {title}\n")
            
            # 处理作者（可选）
            if self.include_authors:
                authors_text = self._extract_authors(paper_json)
                if authors_text:
                    text_parts.append(f"Authors: {authors_text}\n")
            else:
                # 对于peer review，跳过作者信息以避免偏见
                logger.info("跳过作者信息处理（匿名评审模式）")
            
            # 处理发表信息
            publication_text = self._extract_publication(paper_json)
            if publication_text:
                text_parts.append(f"Publication: {publication_text}\n")
            
            # 处理摘要
            abstract_text = self._extract_abstract(paper_json)
            if abstract_text:
                text_parts.append("Abstract:\n")
                text_parts.append(f"{abstract_text}\n")
            
            # 处理正文
            body_text = self._extract_body(paper_json)
            if body_text:
                text_parts.append("\nMain Content:\n")
                text_parts.append(body_text)
            
            # 处理参考文献
            references_text = self._extract_references(paper_json)
            if references_text:
                text_parts.append("\nReferences:\n")
                text_parts.append(references_text)
            
            # 合并文本
            full_text = "\n".join(text_parts)
            
            # 根据参数决定是否截断
            if auto_truncate:
                return self._truncate_to_max_length(full_text)
            else:
                return full_text
            
        except Exception as e:
            logger.error(f"处理JSON论文数据失败: {str(e)}")
            raise RuntimeError(f"处理JSON论文数据失败: {str(e)}")
    
    def process_long_text_with_chunks(self, text: str, query: str, vllm_service) -> str:
        """分块处理长文本"""
        logger.info(f"开始分块处理，文本长度: {len(text)} 字符")
        
        # 检查是否需要分块
        if len(text) <= self.MAX_LENGTH:
            logger.info("文本长度在限制内，直接处理")
            return text
        
        # 分块处理
        chunks = self._split_text_into_chunks(text)
        logger.info(f"文本分为 {len(chunks)} 块")
        
        # 处理每个块
        chunk_reviews = []
        for i, chunk in enumerate(chunks):
            logger.info(f"处理第 {i+1}/{len(chunks)} 块 (长度: {len(chunk)} 字符)")
            
            chunk_query = f"Please provide a preliminary review of the following section (this is part {i+1} of {len(chunks)} parts). Focus on: {query}"
            try:
                chunk_review = vllm_service.generate_peer_review(chunk, chunk_query)
                chunk_reviews.append(f"Section {i+1} Review:\n{chunk_review}")
            except Exception as e:
                logger.error(f"处理第{i+1}块时出错: {str(e)}")
                chunk_reviews.append(f"Section {i+1} processing failed: {str(e)}")
        
        # 合并评审
        combined_reviews = "\n\n".join(chunk_reviews)
        logger.info(f"合并评审: {len(combined_reviews)} 字符")
        
        # 如果合并评审仍然过长，则递归处理
        if len(combined_reviews) > self.MAX_LENGTH:
            logger.info("Combined reviews still too long, performing final synthesis")
            return self.process_long_text_with_chunks(combined_reviews, 
                                                    f"Please synthesize the following section reviews into a comprehensive peer review focusing on: {query}", 
                                                    vllm_service)
        
        # 最终评审
        final_query = f"Based on the above section reviews, please provide a comprehensive peer review of the entire paper focusing on: {query}"
        try:
            final_review = vllm_service.generate_peer_review(combined_reviews, final_query)
            logger.info("Chunk-based peer review completed")
            return final_review
        except Exception as e:
            logger.error(f"Error during final review synthesis: {str(e)}")
            return f"Peer review synthesis completed, but final analysis failed: {str(e)}\n\nSection Reviews:\n{combined_reviews}"
    
    def process_long_text_with_chunks_stream(self, text: str, query: str, vllm_service) -> Generator[str, None, None]:
        """分块处理长文本 - 流式版本"""
        logger.info(f"开始流式分块处理，文本长度: {len(text)} 字符")
        
        # 检查是否需要分块
        if len(text) <= self.MAX_LENGTH:
            logger.info("文本长度在限制内，直接流式处理")
            for chunk in vllm_service.generate_peer_review_stream(text, query):
                yield chunk
            return
        
        # 分块处理
        chunks = self._split_text_into_chunks(text)
        logger.info(f"文本分为 {len(chunks)} 块")
        
        # 流式处理每个块
        chunk_reviews = []
        for i, chunk in enumerate(chunks):
            logger.info(f"流式处理第 {i+1}/{len(chunks)} 块 (长度: {len(chunk)} 字符)")
            
            yield f"\n\n=== Processing Section {i+1}/{len(chunks)} ===\n"
            
            chunk_query = f"Please provide a preliminary review of the following section (this is part {i+1} of {len(chunks)} parts). Focus on: {query}"
            
            try:
                section_content = []
                for content_chunk in vllm_service.generate_peer_review_stream(chunk, chunk_query):
                    yield content_chunk
                    section_content.append(content_chunk)
                
                # 保存完整的块评审用于最终合成
                chunk_reviews.append(f"Section {i+1} Review:\n{''.join(section_content)}")
                
            except Exception as e:
                logger.error(f"处理第{i+1}块时出错: {str(e)}")
                error_msg = f"Section {i+1} processing failed: {str(e)}"
                yield f"\n[ERROR: {error_msg}]\n"
                chunk_reviews.append(error_msg)
        
        # 最终合成评审
        yield f"\n\n=== Generating Final Comprehensive Review ===\n"
        
        combined_reviews = "\n\n".join(chunk_reviews)
        logger.info(f"开始最终合成评审，合并内容长度: {len(combined_reviews)} 字符")
        
        # 如果合并评审仍然过长，则递归处理
        if len(combined_reviews) > self.MAX_LENGTH:
            logger.info("Combined reviews still too long, performing final synthesis")
            for chunk in self.process_long_text_with_chunks_stream(
                combined_reviews, 
                f"Please synthesize the following section reviews into a comprehensive peer review focusing on: {query}", 
                vllm_service
            ):
                yield chunk
        else:
            # 最终评审
            final_query = f"Based on the above section reviews, please provide a comprehensive peer review of the entire paper focusing on: {query}"
            try:
                for final_chunk in vllm_service.generate_peer_review_stream(combined_reviews, final_query):
                    yield final_chunk
                logger.info("Streaming chunk-based peer review completed")
            except Exception as e:
                logger.error(f"Error during final review synthesis: {str(e)}")
                yield f"\n[ERROR: Final synthesis failed: {str(e)}]\n"
                yield f"\nSection Reviews:\n{combined_reviews}"
    
    def _split_text_into_chunks(self, text: str) -> List[str]:
        """将文本分割成重叠块"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.CHUNK_SIZE
            
            # 最后一块包含所有剩余内容
            if end >= len(text):
                chunks.append(text[start:])
                break
            
            # 在句子边界分割
            chunk_end = self._find_sentence_boundary(text, start, end)
            chunk = text[start:chunk_end]
            chunks.append(chunk)
            
            # 下一块开始位置
            start = chunk_end - self.CHUNK_OVERLAP
            start = max(0, start)
        
        return chunks
    
    def _find_sentence_boundary(self, text: str, start: int, preferred_end: int) -> int:
        """在句子边界分割"""
        search_start = max(start, preferred_end - 200)
        search_end = min(len(text), preferred_end + 200)
        
        sentence_endings = ['.', '。', '!', '！', '?', '？', '\n\n']
        
        # 向后搜索句子结束
        for i in range(preferred_end, search_end):
            if text[i] in sentence_endings:
                return i + 1
        
        # 向前搜索句子结束
        for i in range(preferred_end, search_start, -1):
            if text[i] in sentence_endings:
                return i + 1
        
        return preferred_end
    
    def _truncate_to_max_length(self, text: str) -> str:
        """截断到最大长度"""
        if len(text) <= self.MAX_LENGTH:
            return text
        
        return text[:self.MAX_LENGTH - 100] + "..."

    def _extract_title(self, paper_json: Dict[str, Any]) -> str:
        """提取标题"""
        return paper_json.get('title', '').strip()

    def _extract_authors(self, paper_json: Dict[str, Any]) -> str:
        """提取作者"""
        authors = paper_json.get('author', [])
        if not isinstance(authors, list):
            return ""
        
        author_names = []
        for author in authors:
            if isinstance(author, dict):
                name = author.get('name', '').strip()
                if name:
                    author_names.append(name)
            elif isinstance(author, str):
                author_names.append(author.strip())
        
        return ', '.join(author_names)

    def _extract_publication(self, paper_json: Dict[str, Any]) -> str:
        """提取发表信息"""
        publication = paper_json.get('publication', {})
        if not isinstance(publication, dict):
            return ""
        
        pub_parts = []
        
        # 发表日期
        date = publication.get('date', '').strip()
        if date:
            pub_parts.append(f"Publication Date: {date}")
        
        # 发表者
        publisher = publication.get('publisher', {})
        if isinstance(publisher, dict):
            pub_name = publisher.get('name', '').strip()
            if pub_name:
                pub_parts.append(f"Publisher: {pub_name}")
        
        return ', '.join(pub_parts)
    
    def _extract_abstract(self, paper_json: Dict[str, Any]) -> str:
        """提取摘要"""
        abstract = paper_json.get('abstract', [])
        if not isinstance(abstract, list):
            return ""
        
        abstract_parts = []
        for abstract_item in abstract:
            if isinstance(abstract_item, list) and abstract_item:
                abstract_parts.append(str(abstract_item[0]).strip())
            elif isinstance(abstract_item, str):
                abstract_parts.append(abstract_item.strip())
        
        return '\n'.join(abstract_parts)
    
    def _extract_body(self, paper_json: Dict[str, Any]) -> str:
        """提取正文"""
        body = paper_json.get('body', [])
        if not isinstance(body, list):
            return ""
        
        body_parts = []
        for section in body:
            if not isinstance(section, dict):
                continue
            
            # 章节标题
            section_title = self._extract_section_title(section)
            if section_title:
                body_parts.append(f"\n{section_title}")
            
            # 段落内容
            paragraphs = self._extract_paragraphs(section)
            if paragraphs:
                body_parts.extend(paragraphs)
        
        return '\n'.join(body_parts)
    
    def _extract_section_title(self, section: Dict[str, Any]) -> str:
        """提取章节标题"""
        section_info = section.get('section', {})
        if not isinstance(section_info, dict):
            return ""
        
        # 处理index字段，可能是字符串、整数或其他类型
        index_raw = section_info.get('index', '')
        index = str(index_raw).strip() if index_raw is not None else ''
        
        # 处理name字段
        name_raw = section_info.get('name', '')
        name = str(name_raw).strip() if name_raw is not None else ''
        
        # 特殊处理：如果index是-1，通常表示没有编号
        if index == '-1':
            index = ''
        
        if index and name:
            return f"{index} {name}"
        elif name:
            return name
        elif index:
            return index
        
        return ""
    
    def _extract_paragraphs(self, section: Dict[str, Any]) -> List[str]:
        """提取段落"""
        paragraphs = section.get('p', [])
        if not isinstance(paragraphs, list):
            return []
        
        paragraph_texts = []
        for paragraph in paragraphs:
            if isinstance(paragraph, dict):
                text = paragraph.get('text', '').strip()
                if text:
                    paragraph_texts.append(text)
            elif isinstance(paragraph, str):
                text = paragraph.strip()
                if text:
                    paragraph_texts.append(text)
        
        return paragraph_texts
    
    def _extract_references(self, paper_json: Dict[str, Any]) -> str:
        """提取参考文献"""
        references = paper_json.get('reference', [])
        if not isinstance(references, list):
            return ""
        
        ref_parts = []
        for i, ref in enumerate(references):
            if isinstance(ref, dict):
                # 提取引用信息
                title = ref.get('title', '').strip()
                authors = ref.get('authors', [])
                year = ref.get('year', '').strip()
                
                ref_text = f"[{i+1}]"
                if title:
                    ref_text += f" {title}"
                if authors:
                    if isinstance(authors, list):
                        author_names = [str(author).strip() for author in authors if str(author).strip()]
                        if author_names:
                            ref_text += f", {', '.join(author_names)}"
                    else:
                        ref_text += f", {str(authors).strip()}"
                if year:
                    ref_text += f", {year}"
                
                ref_parts.append(ref_text)
            elif isinstance(ref, str):
                ref_parts.append(f"[{i+1}] {ref.strip()}")
        
        return '\n'.join(ref_parts)
