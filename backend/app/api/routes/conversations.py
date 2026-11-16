"""Saved conversations: create, list, open, rename, delete, and choose their documents."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.conversation_store import Conversation, ConversationStore, get_conversation_store
from app.db.vector_store import VectorStore, get_vector_store
from app.schemas.conversations import (
    ConversationDocument,
    ConversationDocumentsResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationSummary,
    CreateConversationRequest,
    MessageResponse,
    RenameConversationRequest,
    SavedSource,
    SetDocumentsRequest,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _get_or_404(conversations: ConversationStore, conversation_id: int) -> Conversation:
    conversation = conversations.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return conversation


def _existing_documents_or_404(
    document_ids: list[str], store: VectorStore
) -> list[ConversationDocument]:
    """Check that every id is a stored document. Duplicate ids in the request are ignored."""
    unique_ids = list(dict.fromkeys(document_ids))  # removes repeats, keeps the order
    found = store.find_documents(unique_ids)
    if len(found) != len(unique_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more documents were not found.")
    return [ConversationDocument(document_id=d.document_id, filename=d.filename) for d in found]


def _summary(conversation: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id, title=conversation.title, updated_at=conversation.updated_at
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConversationResponse)
def create_conversation(
    request: CreateConversationRequest | None = None,  # the body is optional
    conversations: ConversationStore = Depends(get_conversation_store),
    store: VectorStore = Depends(get_vector_store),
) -> ConversationResponse:
    document_ids = request.document_ids if request else []
    documents = _existing_documents_or_404(document_ids, store)
    conversation = conversations.create_conversation([d.document_id for d in documents])
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        documents=documents,
        messages=[],
    )


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    conversations: ConversationStore = Depends(get_conversation_store),
) -> ConversationListResponse:
    return ConversationListResponse(
        conversations=[_summary(c) for c in conversations.list_conversations()]
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: int,
    conversations: ConversationStore = Depends(get_conversation_store),
    store: VectorStore = Depends(get_vector_store),
) -> ConversationResponse:
    conversation = _get_or_404(conversations, conversation_id)
    selected_ids = conversations.get_document_ids(conversation_id)
    messages = conversations.get_messages(conversation_id)

    # One ChromaDB lookup for every document this conversation mentions (selected
    # or cited in an old answer), to learn which ones still exist.
    cited_ids = {source["document_id"] for m in messages for source in m.sources}
    existing = {
        d.document_id: d for d in store.find_documents(sorted(set(selected_ids) | cited_ids))
    }

    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        documents=[
            ConversationDocument(document_id=d.document_id, filename=d.filename)
            for d in existing.values()
            if d.document_id in selected_ids
        ],
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                found=m.found,
                sources=[
                    # Old answers keep their sources even after a document is deleted:
                    # the filename was saved with the message, so it can still be shown.
                    SavedSource(**source, document_deleted=source["document_id"] not in existing)
                    for source in m.sources
                ],
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.patch("/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(
    conversation_id: int,
    request: RenameConversationRequest,
    conversations: ConversationStore = Depends(get_conversation_store),
) -> ConversationSummary:
    _get_or_404(conversations, conversation_id)
    return _summary(conversations.rename_conversation(conversation_id, request.title))


@router.put("/{conversation_id}/documents", response_model=ConversationDocumentsResponse)
def set_conversation_documents(
    conversation_id: int,
    request: SetDocumentsRequest,
    conversations: ConversationStore = Depends(get_conversation_store),
    store: VectorStore = Depends(get_vector_store),
) -> ConversationDocumentsResponse:
    """Replace the conversation's whole document selection ([] clears it)."""
    _get_or_404(conversations, conversation_id)
    documents = _existing_documents_or_404(request.document_ids, store)
    conversations.set_document_ids(conversation_id, [d.document_id for d in documents])
    return ConversationDocumentsResponse(documents=documents)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    conversations: ConversationStore = Depends(get_conversation_store),
) -> None:
    """Deletes the conversation and its messages. The documents themselves are not touched."""
    if not conversations.delete_conversation(conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_conversations(
    conversations: ConversationStore = Depends(get_conversation_store),
) -> None:
    """Deletes every conversation and message. The documents themselves are not touched."""
    conversations.delete_all_conversations()
