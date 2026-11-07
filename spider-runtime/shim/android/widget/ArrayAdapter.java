package android.widget;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class ArrayAdapter<T> extends BaseAdapter {

    private final Context context;
    private final int resource;
    private final List<T> items;

    public ArrayAdapter(Context context, int resource) {
        this(context, resource, new ArrayList<>());
    }

    public ArrayAdapter(Context context, int resource, List<T> items) {
        this.context = context;
        this.resource = resource;
        this.items = items == null ? new ArrayList<>() : items;
    }

    public ArrayAdapter(Context context, int resource, int textViewResourceId, List<T> items) {
        this(context, resource, items);
    }

    public Context getContext() { return context; }

    public int getResource() { return resource; }

    @Override
    public int getCount() { return items.size(); }

    @Override
    public T getItem(int position) { return items.get(position); }

    @Override
    public long getItemId(int position) { return position; }

    @Override
    public View getView(int position, View convertView, ViewGroup parent) { return convertView; }

    public void add(T object) {
        items.add(object);
        notifyDataSetChanged();
    }

    public void addAll(Collection<? extends T> values) {
        items.addAll(values);
        notifyDataSetChanged();
    }

    public void addAll(T... values) {
        for (T value : values) items.add(value);
        notifyDataSetChanged();
    }

    public void insert(T object, int index) {
        items.add(index, object);
        notifyDataSetChanged();
    }

    public void remove(T object) {
        items.remove(object);
        notifyDataSetChanged();
    }

    public void clear() {
        items.clear();
        notifyDataSetChanged();
    }

    public void setNotifyOnChange(boolean notifyOnChange) {
    }

    public void setDropDownViewResource(int resource) {
    }
}
