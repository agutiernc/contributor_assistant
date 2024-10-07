import streamlit as st
import time
import uuid
import matplotlib.pyplot as plt

from assistant import get_answer
from db import (
    save_conversation,
    save_feedback,
    get_recent_conversations,
    get_feedback_stats,
)

def print_log(message):
    print(message, flush=True)

def main():
    print_log("Starting the Hack for LA Contributor Assistant app...")

    st.title("Hack for LA Contributor Assistant")

    # Session state initialization
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = str(uuid.uuid4())
    if "last_conversation_id" not in st.session_state:
        st.session_state.last_conversation_id = None
    if "count" not in st.session_state:
        st.session_state.count = 0
    if "feedback_given" not in st.session_state:
        st.session_state.feedback_given = False

    print_log(f"Current conversation ID: {st.session_state.conversation_id}")

    # Model selection in the sidebar
    model_choice = st.sidebar.selectbox(
        "Select a model:",
        ["claude/3-haiku", "claude/3-5-sonnet"],
    )

    print_log(f"User selected model: {model_choice}")

    # Question input and answer display container
    with st.container():
        user_input = st.chat_input("Enter your question:")

        if user_input:
            print_log(f"User asked: '{user_input}'")

            with st.spinner("Processing..."):
                print_log(f"Getting answer from assistant using {model_choice} model...")

                start_time = time.time()
                answer_data = get_answer(user_input, model_choice)
                end_time = time.time()

                print_log(f"Answer received in {end_time - start_time:.2f} seconds")

                st.success("Completed!")
                st.write(answer_data["answer"])

                # Display monitoring information
                st.write(f"Response time: {answer_data['response_time']:.2f} seconds")
                st.write(f"Relevance: {answer_data['relevance']}")
                st.write(f"Model used: {answer_data['model_used']}")
                st.write(f"Total tokens: {answer_data['total_tokens']}")

                if answer_data["claude_cost"] > 0:
                    st.write(f"Claude AI cost: ${answer_data['claude_cost']:.4f}")

                # Save conversation to database
                print_log("Saving conversation to database")

                save_conversation(st.session_state.conversation_id, user_input, answer_data)
                
                print_log("Conversation saved successfully")

                # Store the last used conversation_id and generate a new one for the next question
                st.session_state.last_conversation_id = st.session_state.conversation_id
                st.session_state.conversation_id = str(uuid.uuid4())
                st.session_state.feedback_given = False

    # Feedback buttons in columns
    col1, col2 = st.columns(2)

    with col1:
        if st.button("+1") and not st.session_state.feedback_given:
            if st.session_state.last_conversation_id:
                st.session_state.count += 1

                print_log(f"Positive feedback received. New count: {st.session_state.count}")
                
                save_feedback(st.session_state.last_conversation_id, 1)
                
                print_log("Positive feedback saved to database")
                
                st.session_state.feedback_given = True
            else:
                st.warning("Please ask a question before providing feedback.")

    with col2:
        if st.button("-1") and not st.session_state.feedback_given:
            if st.session_state.last_conversation_id:
                st.session_state.count -= 1

                print_log(f"Negative feedback received. New count: {st.session_state.count}")
                
                save_feedback(st.session_state.last_conversation_id, -1)
                
                print_log("Negative feedback saved to database")
                
                st.session_state.feedback_given = True
            else:
                st.warning("Please ask a question before providing feedback.")

    st.write(f"Current count: {st.session_state.count}")

    # Recent conversations expander
    with st.expander("Recent Conversations"):
        relevance_filter = st.selectbox(
            "Filter by relevance:", ["All", "RELEVANT", "PARTLY_RELEVANT", "NON_RELEVANT"]
        )

        recent_conversations = get_recent_conversations(
            limit=5, relevance=relevance_filter if relevance_filter != "All" else None
        )

        for conv in recent_conversations:
            st.write(f"Q: {conv['question']}")
            st.write(f"A: {conv['answer']}")
            st.write(f"Relevance: {conv['relevance']}")
            st.write(f"Model: {conv['model_used']}")
            st.write("---")

    # Feedback statistics expander
    with st.expander("Feedback Statistics"):
        feedback_stats = get_feedback_stats()

        st.write(f"Thumbs up: {feedback_stats['thumbs_up']}")
        st.write(f"Thumbs down: {feedback_stats['thumbs_down']}")


    # Pie charts for relevance and user voting
    with st.expander("View Pie Charts for LLM Responses"):
        # Fetch relevance data from recent conversations
        relevance_data = get_recent_conversations(limit=100)
        relevance_count = {'RELEVANT': 0, 'PARTLY_RELEVANT': 0, 'NON_RELEVANT': 0}

        # Count how many responses fall into each relevance category
        for conv in relevance_data:
            if conv['relevance'] == 'RELEVANT':
                relevance_count['RELEVANT'] += 1
            elif conv['relevance'] == 'PARTLY_RELEVANT':
                relevance_count['PARTLY_RELEVANT'] += 1
            elif conv['relevance'] == 'NON_RELEVANT':
                relevance_count['NON_RELEVANT'] += 1
                
        # Create labels and sizes for all categories
        relevance_labels = [label.replace('_', ' ').title() for label in relevance_count.keys()]
        relevance_sizes = list(relevance_count.values())
        
        # Fetch feedback stats (voting data)
        feedback_stats = get_feedback_stats()
        voting_labels = ['Helpful', 'Not Helpful']
        voting_sizes = [feedback_stats['thumbs_up'], feedback_stats['thumbs_down']]
        
        # Create two pie charts side by side
        col1, col2 = st.columns(2)
        
        # Pie chart for relevance
        with col1:
            fig1, ax1 = plt.subplots()

            ax1.pie(relevance_sizes, labels=None, autopct='%1.1f%%', startangle=90)
            ax1.axis('equal')  # Equal aspect ratio ensures the pie is drawn as a circle
            
            # Add a legend to the pie chart with all categories
            ax1.legend(relevance_labels, title="Relevance", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
            
            st.pyplot(fig1)
        
        # Pie chart for user voting
        with col2:
            fig2, ax2 = plt.subplots()

            ax2.pie(voting_sizes, labels=voting_labels, autopct='%1.1f%%', startangle=90)
            ax2.axis('equal')  # Equal aspect ratio ensures the pie is drawn as a circle.
            
            st.pyplot(fig2)

if __name__ == "__main__":
    print_log("Hack for LA Contributor Assistant app started...")
    main()